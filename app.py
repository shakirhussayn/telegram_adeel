import os
import asyncio
import random
import re
from datetime import datetime
from telethon import TelegramClient, events
from telethon.sessions import StringSession

# --- STATE & CLIENTS ---
bot_states = {}
clients = []

def get_template(date, staff_name, daily_num, history_num, location):
    """Creates the final formatted text template."""
    return f"""日期 DATE : {date}
工作员工姓名STAFF NAME: {staff_name}
当日编号 NUMBER OF THE DAY : {daily_num:02}
历史编号 HISTORY NUMBER : {history_num:02}
照片所在地区 PHOTO LOCATION:{location}
"""

def create_photo_handler(account_id):
    """Creates a handler that adds incoming photos to this account's queue."""
    @events.register(events.NewMessage(chats=bot_states[account_id]['source_id']))
    async def photo_handler(event):
        if event.message.photo:
            await bot_states[account_id]['photo_queue'].put(event.message)
            print(f"--- ACCOUNT {account_id}: Photo {event.message.id} added to queue. Queue size is now {bot_states[account_id]['photo_queue'].qsize()} ---")

    return photo_handler

def create_command_handler(account_id):
    """Creates a unique command handler for each account."""
    @events.register(events.NewMessage(chats=bot_states[account_id]['admin_id']))
    async def command_handler(event):
        try:
            command_text = event.message.text.strip().lower()
            state = bot_states[account_id]
            
            if command_text == '/start':
                if not state['is_active']:
                    state['is_active'] = True
                    await event.reply(f"✅ Account {account_id} has been **resumed**.")
                else:
                    await event.reply(f"Account {account_id} is already running.")
            elif command_text == '/stop':
                if state['is_active']:
                    state['is_active'] = False
                    await event.reply(f"🛑 Account {account_id} has been **paused**.")
                else:
                    await event.reply(f"Account {account_id} is already paused.")
            
            # --- NEW: Command to clear the photo queue ---
            elif command_text == '/clearqueue':
                queue_to_clear = bot_states[account_id]['photo_queue']
                count = 0
                while not queue_to_clear.empty():
                    try:
                        queue_to_clear.get_nowait()
                        count += 1
                    except asyncio.QueueEmpty:
                        break
                await event.reply(f"✅ Photo queue cleared. {count} items were removed.")

            elif command_text.startswith('/set'):
                match = re.match(r"/set (.+)=(.+)", command_text, re.IGNORECASE)
                if not match:
                    await event.reply("Invalid format. Use `/set VARIABLE=Value`.")
                    return

                key = match.group(1).strip().upper()
                new_value = match.group(2).strip()
                updated = False
                
                if key == "STAFF_NAME":
                    state['staff_name'] = new_value; updated = True
                elif key == "DATE":
                    state['date'] = new_value; updated = True
                elif key == "PHOTO_LOCATION":
                    state['photo_location'] = new_value; updated = True
                elif key == "START_DAILY_NUM":
                    state['daily_counter'] = int(new_value); updated = True
                elif key == "START_HISTORY_NUM":
                    state['history_counter'] = int(new_value); updated = True
                
                if updated:
                    await event.reply(f"✅ Account {account_id}: {key} updated to '{new_value}'")
                else:
                    await event.reply(f'❌ Unknown setting: {key}')
                
        except Exception as e:
            await event.reply(f"🛑 Error processing command: {e}")
            
    return command_handler

async def photo_worker(account_id):
    """A long-running task that processes photos from one account's queue."""
    state = bot_states[account_id]
    queue = state['photo_queue']
    client = state['client']

    while True:
        message = await queue.get()
        
        while not state['is_active']:
            print(f"--- ACCOUNT {account_id}: Worker is PAUSED. Queue size: {queue.qsize()}. Checking again in 5 seconds... ---")
            await asyncio.sleep(5)
        
        try:
            today_str = datetime.now().strftime("%Y-%m-%d")
            if today_str != state['last_processed_date']:
                print(f"--- ACCOUNT {account_id}: New day! Resetting daily counter. ---")
                state['daily_counter'] = 1
                state['last_processed_date'] = today_str

            print(f"--- ACCOUNT {account_id}: Worker processing Daily #{state['daily_counter']}, History #{state['history_counter']} ---")
            
            template_text = get_template(
                state['date'],
                state['staff_name'],
                state['daily_counter'],
                state['history_counter'],
                state['photo_location']
            )
            
            await client.send_file(
                state['destination_id'],
                message.photo,
                caption=template_text
            )
            
            print(f"  -> ✅ ACCOUNT {account_id}: Successfully posted History #{state['history_counter']}.")
            
            state['daily_counter'] += 1
            state['history_counter'] += 1
            
            delay = random.randint(10, 15)
            print(f"  -> ACCOUNT {account_id}: Waiting for {delay} seconds before next photo...")
            await asyncio.sleep(delay)

        except Exception as e:
            print(f"  -> 🛑 Error processing photo {message.id}: {e}")
        finally:
            queue.task_done()

async def main():
    # A helper function to safely read and clean integer variables
    def get_int_env(key, default=None):
        val = os.environ.get(key)
        if val is None: return default
        return int(re.sub(r'[^\d-]', '', val))

    account_num = 1
    while True:
        # Check for essential account variables
        session_str = os.environ.get(f"TELETHON_SESSION_{account_num}")
        api_id = get_int_env(f"API_ID_{account_num}")
        api_hash = os.environ.get(f"API_HASH_{account_num}")
        if not all([session_str, api_id, api_hash]):
            break
            
        print(f"Initializing configuration for Account #{account_num}")
        client = TelegramClient(StringSession(session_str), api_id, api_hash)
        
        bot_states[account_num] = {
            'client': client,
            'photo_queue': asyncio.Queue(),
            'source_id': get_int_env(f"SOURCE_CHAT_ID_{account_num}"),
            'destination_id': get_int_env(f"DESTINATION_CHAT_ID_{account_num}"),
            'admin_id': get_int_env(f"ADMIN_CHAT_ID_{account_num}"),
            'date': os.environ.get(f"DATE_{account_num}"),
            'staff_name': os.environ.get(f"STAFF_NAME_{account_num}"),
            'photo_location': os.environ.get(f"PHOTO_LOCATION_{account_num}"),
            'history_counter': get_int_env(f"START_HISTORY_NUM_{account_num}", 1),
            'daily_counter': get_int_env(f"START_DAILY_NUM_{account_num}", 1),
            'last_processed_date': datetime.now().strftime("%Y-%m-%d"),
            'is_active': True
        }
        
        client.add_event_handler(create_photo_handler(account_num))
        client.add_event_handler(create_command_handler(account_num))
        clients.append(client)
        
        asyncio.create_task(photo_worker(account_num))
        account_num += 1

    if not clients:
        print("🛑 ERROR: No account configurations found.")
        return

    print(f"\nStarting {len(clients)} bot instance(s)...")
    await asyncio.gather(*(c.start() for c in clients))
    print("✅ All services started and workers are running.")
    await asyncio.gather(*(c.run_until_disconnected() for c in clients))

if __name__ == "__main__":
    asyncio.run(main())
