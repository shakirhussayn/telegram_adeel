import os
import asyncio
import random
import re
from datetime import datetime
from telethon import TelegramClient, events
from telethon.sessions import StringSession
from asyncio import Queue

# --- A helper function to safely read and clean integer variables ---
def get_int_env(key, default=None):
    val = os.environ.get(key)
    if val is None:
        return default
    cleaned_val = re.sub(r'[^\d-]', '', val)
    if cleaned_val:
        return int(cleaned_val)
    return default

# --- CONFIGURATION - Loaded from Railway Environment Variables ---
API_ID = get_int_env("API_ID")
API_HASH = os.environ.get("API_HASH")
SESSION_STRING = os.environ.get("TELETHON_SESSION")

# Template variables
DATE = os.environ.get("DATE", "Not Set")
STAFF_NAME = os.environ.get("STAFF_NAME", "Not Set")
PHOTO_LOCATION = os.environ.get("PHOTO_LOCATION", "Not Set")
START_HISTORY_NUM = get_int_env("START_HISTORY_NUM", 1)
START_DAILY_NUM = get_int_env("START_DAILY_NUM", 1)

# Telegram Channel/Group IDs
ADMIN_CHAT_ID = get_int_env("ADMIN_CHAT_ID")
SOURCE_CHAT_ID = get_int_env("SOURCE_CHAT_ID")
DESTINATION_CHAT_ID = get_int_env("DESTINATION_CHAT_ID")

# --- STATEFUL COUNTERS & QUEUE ---
history_counter = START_HISTORY_NUM
daily_counter = START_DAILY_NUM
last_processed_date = datetime.now().strftime("%Y-%m-%d")
is_active = True
photo_queue = Queue()

# --- TELEGRAM CLIENT ---
client = TelegramClient(StringSession(SESSION_STRING), API_ID, API_HASH)


def get_template(date, staff_name, daily_num, history_num, location):
    """Creates the formatted text template."""
    return f"""日期 DATE : {date}
工作员工姓名STAFF NAME: {staff_name}
当日编号 NUMBER OF THE DAY : {daily_num:02}
历史编号 HISTORY NUMBER : {history_num:02}
照片所在地区 PHOTO LOCATION:{location}
"""

@client.on(events.NewMessage(chats=SOURCE_CHAT_ID))
async def photo_handler(event):
    """This handler's only job is to add incoming photos to the queue."""
    if event.message.photo:
        await photo_queue.put(event.message)
        print(f"-> Photo {event.message.id} added to queue. Queue size is now {photo_queue.qsize()}.")

@client.on(events.NewMessage(chats=ADMIN_CHAT_ID))
async def command_handler(event):
    """Handles all commands sent to the admin chat."""
    global history_counter, daily_counter, DATE, STAFF_NAME, PHOTO_LOCATION, is_active, photo_queue
    command_text = event.message.text.strip().lower()

    if command_text == '/start':
        if not is_active:
            is_active = True
            await event.reply("✅ Bot has been **resumed**. Worker will now process the queue.")
        else:
            await event.reply("Bot is already running.")
    elif command_text == '/stop':
        if is_active:
            is_active = False
            await event.reply("🛑 Bot has been **paused**. It will finish the current photo then wait for /start.")
        else:
            await event.reply("Bot is already paused.")
    elif command_text == '/clearqueue':
        count = 0
        while not photo_queue.empty():
            try:
                photo_queue.get_nowait()
                count += 1
            except asyncio.QueueEmpty:
                break
        await event.reply(f"✅ Photo queue cleared. {count} waiting items were removed.")
    elif command_text.startswith('/set'):
        match = re.match(r"/set (.+)=(.+)", command_text, re.IGNORECASE)
        if not match:
            await event.reply("Invalid format. Use `/set VARIABLE=Value`.")
            return

        key = match.group(1).strip().upper()
        new_value = match.group(2).strip()
        
        if key == "STAFF_NAME": STAFF_NAME = new_value
        elif key == "DATE": DATE = new_value
        elif key == "PHOTO_LOCATION": PHOTO_LOCATION = new_value
        elif key == "START_DAILY_NUM": daily_counter = int(new_value)
        elif key == "START_HISTORY_NUM": history_counter = int(new_value)
        else:
            await event.reply(f'❌ Unknown setting: {key}')
            return
        
        await event.reply(f"✅ Setting updated: {key} is now '{new_value}'")

async def photo_worker():
    """A long-running task that processes photos from the queue."""
    global history_counter, daily_counter, last_processed_date, is_active
    while True:
        # Wait until a photo is available in the queue
        message = await photo_queue.get()
        
        # If the bot is paused, wait here until it's started again
        while not is_active:
            print(f"-> Worker is PAUSED. Queue size: {photo_queue.qsize()}. Checking again in 5 seconds...")
            await asyncio.sleep(5)
        
        try:
            today_str = datetime.now().strftime("%Y-%m-%d")
            if today_str != last_processed_date:
                print("-> New day detected! Resetting daily counter.")
                daily_counter = 1
                last_processed_date = today_str

            print(f"-> Worker processing Daily #{daily_counter}, History #{history_counter}...")
            
            template_text = get_template(DATE, STAFF_NAME, daily_counter, history_counter, PHOTO_LOCATION)
            await client.send_file(DESTINATION_CHAT_ID, message.photo, caption=template_text)
            print(f"  -> ✅ Successfully posted History #{history_counter}.")
            
            daily_counter += 1
            history_counter += 1
            
            delay = random.randint(11, 13)
            print(f"  -> Waiting for {delay} seconds before next photo...")
            await asyncio.sleep(delay)
        except Exception as e:
            print(f"  -> 🛑 Error processing photo {message.id}: {e}")
        finally:
            photo_queue.task_done()

async def main():
    print("Service starting...")
    # Start the background worker task
    asyncio.create_task(photo_worker())
    
    await client.start()
    print(f"✅ Service started. Worker is running. Listening for messages.")
    await client.run_until_disconnected()

if __name__ == "__main__":
    asyncio.run(main())
