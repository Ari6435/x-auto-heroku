# bot_v1.py
"""
X (Twitter) Bot v1 - Affordable Version
- Configurable via config.json (reply count, mix mode, API key, fallbacks)
- Creator list from creators.txt
- Includes Like posts (fixed 30% chance) and Follow creators (fixed 2% chance)
- Human-like behavior simulation
- License validation (Windows Machine GUID)

"""
import datetime
import json
import time
import csv
import os
import random
import re
import sys  # Import sys for exit functionality
from dataclasses import dataclass
from typing import List, Optional, Set
from urllib.parse import quote_plus
# Import the license check module
# import license_check
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver import ActionChains
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import ElementClickInterceptedException, StaleElementReferenceException, TimeoutException
# ========= Gemini through OpenAI SDK =========
from openai import OpenAI
# =========================
# ======= CONFIG (Loaded from files) ==========
# =========================
CONFIG_FILE = "config.json"
CREATORS_FILE = "creators.txt"
def load_config(config_path: str):
    """Load configuration from a JSON file."""
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
        print(f"[i] Loaded configuration from {config_path}")
        return config
    except FileNotFoundError:
        print(f"[!] Error: Configuration file '{config_path}' not found.")
        raise
    except json.JSONDecodeError as e:
        print(f"[!] Error: Invalid JSON in '{config_path}': {e}")
        raise
def load_creators(creators_path: str):
    """Load list of creator handles from a text file."""
    creators = []
    try:
        with open(creators_path, 'r', encoding='utf-8') as f:
            for line in f:
                handle = line.strip().lstrip("@") # Remove leading @ and whitespace
                if handle: # Ignore empty lines
                    creators.append(handle)
        print(f"[i] Loaded {len(creators)} creators from {creators_path}")
    except FileNotFoundError:
        print(f"[!] Warning: Creators file '{creators_path}' not found. Creator list will be empty.")
        # It's not necessarily an error, just means no specific creators to target
    except Exception as e:
        print(f"[!] Error loading creators from '{creators_path}': {e}")
    return creators
# --- Load Config & Creators ---
config_data = load_config(CONFIG_FILE)
CREATOR_USERNAMES = load_creators(CREATORS_FILE)
# --- Assign Config Values ---
# LICENSE_KEY = config_data.get("LICENSE_KEY", "") # Get License Key
MAX_REPLIES_PER_RUN = config_data.get("MAX_REPLIES_PER_RUN", 30)
ENABLE_MIX_MODE = config_data.get("ENABLE_MIX_MODE", True)
MIX_GLOBAL_PERCENT = config_data.get("MIX_GLOBAL_PERCENT", 60)

FALLBACK_QUESTIONS = config_data.get("FALLBACK_QUESTIONS", ["Default Q..."])
FALLBACK_POSITIVE = config_data.get("FALLBACK_POSITIVE", ["Default Pos..."])
FALLBACK_NEGATIVE = config_data.get("FALLBACK_NEGATIVE", ["Default Neg..."])
FALLBACK_GENERAL = config_data.get("FALLBACK_GENERAL", ["Default Gen..."])
COOKIE_FILE = config_data.get("COOKIE_FILE", "rpgamers.json")
OWN_HANDLE = config_data.get("OWN_HANDLE", "")
SEARCH_QUERY = config_data.get("SEARCH_QUERY", " ")
PROCESSED_LOG = config_data.get("PROCESSED_LOG", "processed_tweets_log.csv")
HEADLESS = config_data.get("HEADLESS", False)
ENABLE_LONG_PAUSE = config_data.get("ENABLE_LONG_PAUSE", True)
sysp_optimizer = "Always reply in exactly two lines: first line is your insight, second line is a signature-style attribution. Leave one blank line between."
GEMINI_PROMPT_TEMPLATES = config_data.get("GEMINI_PROMPT_TEMPLATES", [
    f"You are writing a single short reply to a tweet about {{SEARCH_QUERY}}.\nRules:\n- Maximum 15 words.\n- Sound casual and human, not automated.\n- No hashtags, links, or emojis.\n- No em dashes.\n- Keep it conversational.\nTweet: \"{{tweet_text[:600]}}\"\nReply:"
    # Add other default templates here if desired, matching the structure in config.json
])

GEMINI_SYSTEM_PROMPTS = config_data.get("GEMINI_SYSTEM_PROMPTS", [
    "You are a witty, concise social media user who writes one-line replies.",
    "You're chatting casually online. Keep responses short and natural.",
    "Act like a real person responding to tweets. Be conversational."
    # Add other default system prompts here if desired
])
# --- Hardcoded Engagement Probabilities for v1 (Not user-configurable) ---
LIKE_REPLY_PERCENTAGE = config_data.get("LIKE_REPLY_PERCENTAGE", 30)  # Fixed 30% chance to like a post you've replied to (v1)
FOLLOW_CREATOR_PERCENTAGE = 2  # Fixed 2% chance to follow a creator you've replied to (v1)
# --- Internal Constants (Not user-configurable in v1) ---
WAIT_SHORT = 0.5
WAIT_MED = 1.0
WAIT_LONG = 1.7
JITTER_SPREAD = 0.45
TYPE_MIN_DELAY = 0.02
TYPE_MAX_DELAY = 0.08
SCROLL_MIN_FRACTION = 0.55
SCROLL_MAX_FRACTION = 0.65
LONG_PAUSE_EVERY_RANGE = (10, 15)
LONG_PAUSE_DURATION_RANGE = (120, 300)
GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"
GEMINI_MODEL = config_data.get("GEMINI_MODEL","gemini-1.5-flash") # change to 1.5-pro if you want higher quality
print("Gemini model :"+ GEMINI_MODEL)
# --- Multi-API Key Configuration ---
GOOGLE_API_KEYS = config_data.get("GEMINI_API_KEYS", [])
# --- Initialize Clients ---
clients = []
if GOOGLE_API_KEYS:
    for i, key in enumerate(GOOGLE_API_KEYS):
        if key: # Check if key is not empty
            try:
                client_instance = OpenAI(api_key=key, base_url=GEMINI_BASE_URL)
                clients.append(client_instance)
                print(f"[i] Initialized Gemini client {i+1} with provided key.")
            except Exception as e:
                print(f"[!] Failed to initialize Gemini client {i+1}: {e}")
else:
    print("[!] No GOOGLE_API_KEYS configured.")
if not clients:
    print("[!] No valid Gemini clients initialized; replies will use a simple fallback.")
# =========================

# --- Helper Functions ---
def jitter(base: float, spread: float = JITTER_SPREAD) -> float:
    return max(0.1, base + random.uniform(-spread, spread))
def jsleep(base: float, spread: float = JITTER_SPREAD):
    time.sleep(jitter(base, spread))
def random_micro_pause(min_time: float = 0.3, max_time: float = 1.5):
    """Add small random delays between actions"""
    time.sleep(random.uniform(min_time, max_time))
def random_idle_time():
    """Occasionally add longer idle time"""
    if random.random() < 0.1:  # 10% chance
        idle_time = random.uniform(10, 30)  # 10-30 seconds
        print(f"[i] Taking a short break: {idle_time:.1f}s")
        time.sleep(idle_time)
def simulate_reading_time(tweet_text: str) -> float:
    """Calculate realistic reading time based on tweet length"""
    words = len(tweet_text.split())
    # Average reading speed: 200-250 words per minute
    base_time = max(1.0, words / 220.0 * 60)
    # Add some randomness
    return random.uniform(base_time * 0.7, base_time * 1.3)
def should_skip_tweet(tweet_text: str, user_handle: str) -> bool:
    """Randomly decide whether to skip a tweet to appear more human"""
    # 15% chance to skip any tweet
    if random.random() < 0.15:
        print(f"[i] Randomly skipping tweet from @{user_handle}")
        return True
    # Skip if tweet seems low quality
    low_quality_indicators = [
        lambda t: len(t.strip()) < 10,  # Too short
        lambda t: t.count('#') > 3,     # Too many hashtags
        lambda t: 'http' in t.lower(),  # Just a link
        lambda t: all(c in '!?.' for c in t.strip()),  # Just punctuation
    ]
    tweet_lower = tweet_text.lower()
    if any(indicator(tweet_text) for indicator in low_quality_indicators):
        return True
    return False
def should_skip_reply() -> bool:
    """Occasionally skip replying even when we could"""
    # 8% chance to skip replying
    return random.random() < 0.08
# ===== Engagement Probability Functions (Hardcoded for v1) =====
def should_like_reply() -> bool:
    """Determine if we should like a post we just replied to (Fixed 30% for v1)"""
    return random.random() < (LIKE_REPLY_PERCENTAGE / 100.0)
def should_follow_creator() -> bool:
    """Determine if we should follow a creator we just replied to (Fixed 2% for v1)"""
    return random.random() < (FOLLOW_CREATOR_PERCENTAGE / 100.0)
# ===========================================
def simulate_human_browsing(driver: webdriver.Chrome):
    """Simulate human-like browsing behavior"""
    # 20% chance to visit a profile or explore
    if random.random() < 0.20:
        print("[i] Simulating human browsing...")
        # Random actions: visit profile, click hashtag, scroll up/down
        actions = [
            'visit_profile',
            'click_hashtag',
            'scroll_random',
            'read_tweet'
        ]
        action = random.choice(actions)
        if action == 'visit_profile' and random.random() < 0.3:
            # Visit a random user's profile from recent tweets
            try:
                profile_links = driver.find_elements(By.CSS_SELECTOR, 'a[href^="/"][role="link"]')
                if profile_links:
                    link = random.choice(profile_links[:min(5, len(profile_links))])
                    original_url = driver.current_url
                    link.click()
                    jsleep(WAIT_MED, 0.3)
                    # Spend some time on profile
                    time.sleep(random.uniform(2, 5))
                    driver.back()
                    WebDriverWait(driver, 10).until(EC.url_changes(original_url))
                    jsleep(WAIT_MED, 0.3)
            except Exception:
                pass
        elif action == 'click_hashtag' and random.random() < 0.25:
            # Click on a hashtag
            try:
                hashtag_links = driver.find_elements(By.CSS_SELECTOR, 'a[href^="/hashtag/"]')
                if hashtag_links:
                    link = random.choice(hashtag_links[:min(3, len(hashtag_links))])
                    original_url = driver.current_url
                    link.click()
                    jsleep(WAIT_MED, 0.3)
                    time.sleep(random.uniform(1, 3))
                    driver.back()
                    WebDriverWait(driver, 10).until(EC.url_changes(original_url))
                    jsleep(WAIT_MED, 0.3)
            except Exception:
                pass
        elif action == 'scroll_random':
            # Scroll up and down
            driver.execute_script("window.scrollBy(0, -200);")
            jsleep(WAIT_SHORT, 0.2)
            driver.execute_script("window.scrollBy(0, 400);")
            jsleep(WAIT_SHORT, 0.2)
        elif action == 'read_tweet':
            # Simulate reading time
            read_time = random.uniform(1.5, 4.0)
            print(f"[i] Simulating reading time: {read_time:.1f}s")
            time.sleep(read_time)
def send_keys_human_enhanced(driver, text: str):
    """Enhanced human-like typing with typos and corrections"""
    for i, ch in enumerate(text):
        # Occasionally make a typo (3% chance per character)
        if random.random() < 0.03 and ch.isalpha():
            # Type wrong character
            wrong_char = random.choice('abcdefghijklmnopqrstuvwxyz')
            ActionChains(driver).send_keys(wrong_char).perform()
            time.sleep(random.uniform(TYPE_MIN_DELAY, TYPE_MAX_DELAY))
            # Backspace to correct
            ActionChains(driver).send_keys('\b').perform()
            time.sleep(random.uniform(0.05, 0.15))
        # Type correct character
        ActionChains(driver).send_keys(ch).perform()
        time.sleep(random.uniform(TYPE_MIN_DELAY, TYPE_MAX_DELAY))
        # Occasionally pause mid-sentence
        if ch in '.!? ' and random.random() < 0.15:
            time.sleep(random.uniform(0.2, 0.8))
def move_mouse_naturally(driver: webdriver.Chrome, element):
    """Simulate natural mouse movement to an element"""
    try:
        # Get element location
        location = element.location_once_scrolled_into_view
        size = element.size
        # Get current mouse position (approximate)
        current_x = random.randint(100, 500)
        current_y = random.randint(100, 400)
        target_x = location['x'] + size['width'] // 2
        target_y = location['y'] + size['height'] // 2
        # Simulate smooth mouse movement with some randomness
        steps = random.randint(5, 15)
        for i in range(steps):
            progress = i / steps
            # Add some curve to the movement
            x = current_x + (target_x - current_x) * progress + random.randint(-10, 10)
            y = current_y + (target_y - current_y) * progress + random.randint(-10, 10)
            # Note: Selenium doesn't have direct mouse movement control
            # This is a simplified version - you might want to use pyautogui for real mouse control
            time.sleep(random.uniform(0.01, 0.05))
    except Exception:
        pass
def click_element_human(driver, element):
    """Click element with human-like behavior"""
    try:
        # Hover first
        ActionChains(driver).move_to_element(element).perform()
        random_micro_pause(0.1, 0.3)
        # Small pause to simulate decision making
        if random.random() < 0.3:
            time.sleep(random.uniform(0.2, 0.8))
        # Click
        element.click()
    except Exception:
        # Fallback to JavaScript click
        driver.execute_script("arguments[0].click();", element)
# ===== Engagement Functions (Logic included, probabilities fixed) =====
def like_post(driver, article, tweet_id):
    """Attempt to like the given tweet/article robustly."""
    try:
        # Re-locate the article to ensure it's current
        current_article = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located(
                (By.XPATH, f'//article[.//a[contains(@href,"/status/{tweet_id}")]]')
            )
        )
        # Find the like button within the article
        like_button = WebDriverWait(current_article, 10).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, '[data-testid="like"]'))
        )
        # Scroll the button into view to avoid interceptors
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", like_button)
        jsleep(WAIT_SHORT) # Brief pause after scroll
        # Attempt to click
        like_button.click()
        print("[✓] Liked the post.")
        jsleep(WAIT_SHORT) # Wait briefly after action
        return True
    except (ElementClickInterceptedException, StaleElementReferenceException) as e:
        print(f"[!] Like click intercepted or stale for {tweet_id}. Retrying...")
        try:
            # Retry scroll and click
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", like_button)
            jsleep(WAIT_SHORT)
            driver.execute_script("arguments[0].click();", like_button) # JS click as fallback
            print("[✓] Liked the post (JS click).")
            jsleep(WAIT_SHORT)
            return True
        except Exception as e2:
            print(f"[!] Could not like post {tweet_id} after retry: {e2}")
            return False
    except TimeoutException as e:
        print(f"[!] Timeout finding like button for {tweet_id}: {e}")
        return False
    except Exception as e:
        print(f"[!] Could not like post {tweet_id}: {e}")
        return False

def follow_creator(driver, user_handle):
    """Attempt to follow the creator robustly."""
    original_url = driver.current_url # Store original URL to return
    try:
        # Navigate to the user's profile page
        profile_url = f"https://x.com/{user_handle}"
        driver.get(profile_url)
        WebDriverWait(driver, 20).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, 'div[data-testid="primaryColumn"]')) # Wait for profile main content
        )
        jsleep(WAIT_MED) # Wait for profile to load

        # Find the follow/unfollow button using a more robust selector
        # Look for a button whose data-testid contains 'follow'
        follow_button = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, 'button[data-testid*="follow"]'))
        )

        # Check button state using data-testid for reliability
        data_testid = follow_button.get_attribute("data-testid") or ""
        if "unfollow" in data_testid.lower():
            print(f"[i] Already following @{user_handle}.")
            return True # Consider this a success

        # Scroll the button into view
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", follow_button)
        jsleep(WAIT_SHORT)

        # Attempt to click
        follow_button.click()
        print(f"[✓] Followed @{user_handle}.")
        jsleep(WAIT_SHORT) # Wait briefly after action
        return True

    except (ElementClickInterceptedException, StaleElementReferenceException) as e:
        print(f"[!] Follow click intercepted or stale for @{user_handle}. Retrying...")
        try:
            # Retry scroll and click
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", follow_button)
            jsleep(WAIT_SHORT)
            driver.execute_script("arguments[0].click();", follow_button) # JS click as fallback
            print(f"[✓] Followed @{user_handle} (JS click).")
            jsleep(WAIT_SHORT)
            return True
        except Exception as e2:
            print(f"[!] Could not follow @{user_handle} after retry: {e2}")
            return False
    except TimeoutException as e:
        print(f"[!] Timeout finding follow button for @{user_handle}: {e}")
        return False
    except Exception as e:
         print(f"[!] Could not follow @{user_handle}: {e}")
         return False
    finally:
        # Always attempt to go back to the previous page (the tweet)
        try:
            # Use back() for more natural navigation, fallback to direct URL
            driver.back()
            # Wait for URL to change and indicate we are likely back on a tweet or feed page
            WebDriverWait(driver, 20).until_not(EC.url_to_be(profile_url))
            jsleep(WAIT_MED)
            # Optional: Add an extra check if the URL is as expected or page loaded correctly
        except Exception as e:
            print(f"[!] Warning: Could not navigate back after follow attempt for @{user_handle}: {e}")
            # If back() fails, try navigating directly to the original URL
            try:
                driver.get(original_url)
                WebDriverWait(driver, 20).until(EC.url_contains("/status/") | EC.url_contains("/search/")) # Wait for a relevant page
                jsleep(WAIT_MED)
            except Exception as e2:
                 print(f"[!] Critical Error: Could not restore original page after follow attempt for @{user_handle}: {e2}")
                 # Consider raising an exception or marking the session as unstable

# =================================
# def _sanitize_reply(text: str) -> str:
#     if not text:
#         return "Nice point , thanks for sharing!"
#     text = text.replace("—", "-").replace("–", "-").replace("!", " ").replace("'s"," ").replace(";","").replace("*","").replace("wow","").replace(","," ")
#     text = re.sub(r"https?://\S+", "", text)
#     text = re.sub(r"\s+#\S+", "", text)
#     text = re.sub(r"\s+", " ", text).strip()
#     words = text.split()
#     if len(words) > 15:
#         text = " ".join(words[:15])
#     text = re.sub(r"[.!?]{3,}$", "!", text)
#     return text or "Nice point, thanks for sharing!"



# --- Reply Sanitization (Updated for 2-line format) ---
def _sanitize_reply(text: str) -> str:
    """Clean up the generated reply and format it as two lines with specific capitalization."""
    if not text:
        return "Interesting point, thanks for sharing"

    # Basic cleanup (remove links, hashtags, excessive punctuation)
    text = text.replace("—", "-").replace("–", "-").replace("!", " ").replace("'s"," ").replace(";","").replace("*","").replace("wow","").replace(","," ").replace("Sounds"," ")
    text = re.sub(r"https?://\S+", "", text) # Remove links
    text = re.sub(r"\s+#\S+", "", text)      # Remove hashtags
    text = re.sub(r"[^\w\s\-!?.,'\"]", " ", text) # Remove most special chars except common punctuation and hyphen
    text = re.sub(r"\s+", " ", text).strip() # Normalize whitespace

    # Split into lines based on newlines or sentence endings
    lines = []
    # Attempt to split by newlines first (in case model generated them)
    potential_lines = text.splitlines()
    if len(potential_lines) >= 2:
        # If AI generated multiple lines, take the first two non-empty ones
        lines = [line.strip() for line in potential_lines if line.strip()][:2]
    else:
        # If not, try splitting by sentence endings
        sentences = re.split(r"[.!?]+", text)
        sentences = [s.strip() for s in sentences if s.strip()]
        if len(sentences) >= 2:
            lines = sentences[:2]
        else:
            # If still only one part, split it roughly in the middle if long enough, or use as is
            single_line = sentences[0] if sentences else text
            words = single_line.split()
            if len(words) > 8: # Arbitrary threshold to split a single sentence
                 mid = len(words) // 2
                 lines = [" ".join(words[:mid]), " ".join(words[mid:])]
            else:
                 lines = [single_line, ""] # Second line will be empty/default


    # Limit total words
    all_words = []
    for line in lines:
        all_words.extend(line.split())
    if len(all_words) > 18: # Slightly higher word limit for 2 lines
        all_words = all_words[:18]
    # Rebuild lines ensuring two lines
    if len(all_words) > 9:
        line1_words = all_words[:len(all_words)//2]
        line2_words = all_words[len(all_words)//2:]
    else:
        line1_words = all_words
        line2_words = [" "] # Default signature if second part is too short/missing

    line1 = " ".join(line1_words)
    line2 = " ".join(line2_words)

    # Combine into the final two-line format
    formatted_reply = f"{line1}\n\n{line2}"

    # --- Human-like capitalization: Only the very first letter is uppercase ---
    formatted_reply = formatted_reply.lower()
    if formatted_reply:
        formatted_reply = formatted_reply[0].upper() + formatted_reply[1:]

    # Final check to avoid returning an empty or nearly empty string
    final_reply = formatted_reply.strip()
    if not final_reply or len(final_reply) < 5:
        return "🔥\n\n"

    return final_reply
#======================================================================

def analyze_tweet_context(tweet_text: str) -> dict:
    """Analyze tweet for context-aware replies"""
    text_lower = tweet_text.lower()
    context = {
        'is_question': any(q in text_lower for q in ['?', 'what do you think', 'how do you', 'anyone tried']),
        'is_positive': any(word in text_lower for word in ['awesome', 'great', 'love', 'amazing', 'cool', 'nice']),
        'is_negative': any(word in text_lower for word in ['hate', 'terrible', 'bad', 'worst', 'annoying']),
        'is_technical': any(word in text_lower for word in ['api', 'code', 'sdk', 'integration', 'developer']),
        'mentions_tool': SEARCH_QUERY.lower() in text_lower, # Use SEARCH_QUERY
        'has_exclamation': '!' in tweet_text
    }
    return context


# ===== Updated Fallback Reply Function (Uses Config) =====
def get_contextual_fallback(context: dict) -> str:
    """Get contextually appropriate fallback reply using user-configured messages."""
    if context['is_question']:
        return random.choice(FALLBACK_QUESTIONS) # Use configured list
    elif context['is_positive']:
        return random.choice(FALLBACK_POSITIVE) # Use configured list
    elif context['is_negative']:
        return random.choice(FALLBACK_NEGATIVE) # Use configured list
    else:
        return random.choice(FALLBACK_GENERAL) # Use configured list
# ===========================================
# # ===== Updated Gemini Reply Function (Single Key) =====
# def generate_reply_with_gemini_enhanced(tweet_text: str) -> str:
#     """Generate reply using the single configured Gemini API key."""
#     # Use the globally initialized single client
#     if client is None:
#         return _sanitize_reply(get_contextual_fallback({
#             'is_question': False, 'is_positive': False,
#             'is_negative': False, 'is_technical': False,
#             'mentions_tool': True, 'has_exclamation': False
#         }))
#     # Multiple prompt templates for variety
#     if not GEMINI_PROMPT_TEMPLATES:
#         print("[!] Warning: GEMINI_PROMPT_TEMPLATES list is empty in config. Using default template.")
#         prompt_templates = [f"You are writing a single short reply to a tweet about {{SEARCH_QUERY}}.\nRules:\n- Maximum 15 words.\n- Sound casual and human, not automated.\n- No hashtags, links, or emojis.\n- No em dashes.\n- Keep it conversational.\nTweet: \"{{tweet_text[:600]}}\"\nReply:"]
#     else:
#         prompt_templates = GEMINI_PROMPT_TEMPLATES

#     if not GEMINI_SYSTEM_PROMPTS:
#         print("[!] Warning: GEMINI_SYSTEM_PROMPTS list is empty in config. Using default system prompt.")
#         system_prompts = ["You are a witty, concise social media user who writes one-line replies."]
#     else:
#         system_prompts = GEMINI_SYSTEM_PROMPTS # Use the system prompts from config

#     #take a random perompt template and system prompt
#     prompt_template = random.choice(prompt_templates)
#     system_prompt = random.choice(system_prompts)

#     # Format the selected template with the actual tweet text
#     # Ensure tweet_text is a string and handle potential None (though unlikely here)
#     formatted_tweet_text = (tweet_text or "")[:600]
#     print("formatted_tweet_text"+ f"{formatted_tweet_text}")
#     prompt = prompt_template.format(search_query=SEARCH_QUERY,tweet_text=formatted_tweet_text)

#     try:
#         resp = client.chat.completions.create(
#             model=GEMINI_MODEL,
#             messages=[
#                 {"role": "system", "content": system_prompt},
#                 {"role": "user", "content": prompt},
#             ],
#             max_tokens=40,
#             temperature=random.uniform(0.7, 0.9),  #Add temperature variation
#             stop=["\n"],
#         ) 
#         reply = (resp.choices[0].message.content or "").strip()
#         return _sanitize_reply(reply)
#     except Exception as e:
#         print(f"[!] Gemini failed, fallback used: {e}")
#         return _sanitize_reply(get_contextual_fallback({
#             'is_question': False, 'is_positive': False,
#             'is_negative': False, 'is_technical': False,
#             'mentions_tool': True, 'has_exclamation': False
#         }))


# ===== Updated Gemini Reply Function (Multi-Key with Prompt Templates) =====
def generate_reply_with_gemini_enhanced(tweet_text: str) -> str:
    """Generate reply using multiple Gemini API keys with prompt template support."""
    # Check if any clients are available
    if not clients:
        return _sanitize_reply(get_contextual_fallback({
            'is_question': False, 'is_positive': False,
            'is_negative': False, 'is_technical': False,
            'mentions_tool': True, 'has_exclamation': False
        }))
    
    # Multiple prompt templates for variety
    if not GEMINI_PROMPT_TEMPLATES:
        print("[!] Warning: GEMINI_PROMPT_TEMPLATES list is empty in config. Using default template.")
        prompt_templates = [f"You are writing a single short reply to a tweet about {SEARCH_QUERY}.\nRules:\n- Maximum 15 words.\n- Sound casual and human, not automated.\n- No hashtags, links, or emojis.\n- No em dashes.\n- Keep it conversational.\nTweet: \"{{tweet_text[:600]}}\"\nReply:"]
    else:
        prompt_templates = GEMINI_PROMPT_TEMPLATES

    if not GEMINI_SYSTEM_PROMPTS:
        print("[!] Warning: GEMINI_SYSTEM_PROMPTS list is empty in config. Using default system prompt.")
        system_prompts = ["You are a witty, concise social media user who writes one-line replies."]
    else:
        # Use the system prompts from config
        system_prompts = GEMINI_SYSTEM_PROMPTS
    # Take a random prompt template and system prompt
    prompt_template = random.choice(prompt_templates) + "Avoid links, hashtags, emojis, or fancy punctuation"
    system_prompt = sysp_optimizer + random.choice(system_prompts) 

    # Format the selected template with the actual tweet text
    # Ensure tweet_text is a string and handle potential None (though unlikely here)
    formatted_tweet_text = (tweet_text or "")[:600]
    # prompt = prompt_template.format(search_query=SEARCH_QUERY, tweet_text=formatted_tweet_text)
    # print(prompt)
    prompt = (
        f"You are writing a short, casual reply to a tweet. "
        f"Rules: "
        f"1. Maximum 18 words total. "
        f"2. Format your reply EXACTLY as follows: "
        f"[First line: your main thought or reaction] "
        f"[Second line: a short signature or attribution (e.g., '- a fellow dev', '- curious mind', '- seen this too')] "
        f"3. Use natural, conversational language. "
        f"4. No hashtags, links, emojis, or fancy punctuation. "
        f"5. No markdown or formatting. "
        f"Tweet: \"{formatted_tweet_text}\" "
        f"Reply:"
    )    

    # --- Try each client until one succeeds ---
    last_exception = None
    for i, client_instance in enumerate(clients):
        try:
            resp = client_instance.chat.completions.create(
                model=GEMINI_MODEL,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt},
                ],
                max_tokens=40,
                temperature=random.uniform(0.7, 0.9),  # Add temperature variation
                stop=["\n"],
            )
            reply = (resp.choices[0].message.content or "").strip()
            # print(f"[i] Successfully used Gemini client {i+1}.") # Optional debug log
            return _sanitize_reply(reply)
        except Exception as e:
            # print(f"[!] Gemini client {i+1} failed: {e}") # Optional debug log
            last_exception = e  # Store the last error
            # Continue to the next client
    # If all clients failed
    print(f"[!] All Gemini clients failed. Last error: {last_exception}")
    return _sanitize_reply(get_contextual_fallback({
        'is_question': False, 'is_positive': False,
        'is_negative': False, 'is_technical': False,
        'mentions_tool': True, 'has_exclamation': False
    }))
# ===========================================
@dataclass
class TweetCandidate:
    tweet_id: str
    tweet_url: str
    user_handle: str
    text: str
# ===== Selenium helpers =====
def setup_driver() -> webdriver.Chrome:
    """Enhanced driver setup with anti-detection measures for single account"""
    opts = Options()
    if HEADLESS:
        opts.add_argument("--headless=new")
    # Essential options + GPU error suppression
    opts.add_argument("--disable-gpu")
    opts.add_argument("--disable-software-rasterizer")
    opts.add_argument("--disable-background-timer-throttling")
    opts.add_argument("--disable-backgrounding-occluded-windows")
    opts.add_argument("--disable-renderer-backgrounding")
    opts.add_argument("--disable-ipc-flooding-protection")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--lang=en-US")
    opts.add_argument("--disable-extensions")
    opts.add_argument("--disable-plugins")
    opts.add_argument("--disable-images")
    opts.add_argument("--blink-settings=imagesEnabled=false")
    # opts.add_argument("--disable-images") # Uncomment if needed
    # opts.add_argument("--disable-javascript") # Remove if you need JS
    # Suppress logging
    opts.add_argument("--log-level=3")  # Only show fatal errors
    opts.add_argument("--silent")
    opts.add_experimental_option('excludeSwitches', ['enable-logging'])
    opts.add_experimental_option('useAutomationExtension', False)
    # Anti-detection options
    opts.add_argument("--disable-blink-features=AutomationControlled")
    opts.add_experimental_option("excludeSwitches", ["enable-automation"])
    # FIXED user-agent (consistent for single account)
    opts.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36")
    driver = webdriver.Chrome(options=opts)
    driver.set_page_load_timeout(45)
    # Execute scripts to hide automation
    driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
    driver.execute_script("""
        Object.defineProperty(navigator, 'plugins', {
            get: () => [1, 2, 3, 4, 5]
        });
    """)
    return driver
def load_cookies_from_file(path: str) -> List[dict]:
    with open(path, "r", encoding="utf-8") as f:
        cookies = json.load(f)
    for c in cookies:
        c.pop("sameSite", None)
    return cookies
def inject_cookies(driver: webdriver.Chrome, cookies: List[dict]):
    driver.get("https://x.com/home")
    jsleep(WAIT_MED)
    for c in cookies:
        try:
            driver.add_cookie(c)
        except Exception:
            c2 = dict(c)
            if c2.get("domain", "").startswith("."):
                c2["domain"] = c2["domain"][1:]
            c2.pop("sameSite", None)
            try:
                driver.add_cookie(c2)
            except Exception:
                pass
    driver.get("https://x.com/home")
def save_refreshed_cookies(driver: webdriver.Chrome, path: str):
    try:
        cookies = driver.get_cookies()
        with open(path, "w", encoding="utf-8") as f:
            json.dump(cookies, f, indent=2)
        print(f"[i] Saved refreshed cookies -> {path}")
    except Exception as e:
        print(f"[!] Could not save refreshed cookies: {e}")
def ensure_logged_in(driver: webdriver.Chrome, timeout: int = 15) -> bool:
    try:
        WebDriverWait(driver, timeout).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, '[data-testid="SideNav_AccountSwitcher_Button"]'))
        )
        print("[✓] Confirmed logged-in UI present.")
        return True
    except Exception:
        print("[!] Could not confirm logged-in UI.")
        return False
def read_processed_ids(path: str) -> Set[str]:
    if not os.path.exists(path):
        return set()
    ids = set()
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.reader(f):
            if not row:
                continue
            ids.add(row[0])
    return ids
def append_processed_id(path: str, tweet_id: str):
    with open(path, "a", newline="", encoding="utf-8") as f:
        csv.writer(f).writerow([tweet_id])
# ---------- Only ORIGINAL posts ----------
def is_original_post(article) -> bool:
    """
    Heuristics to exclude replies/retweets/quotes:
    - No 'Replying to' text in or near the header
    - No socialContext (liked/reposted)
    - No embedded quoted-tweet card
    """
    try:
        sc = article.find_elements(By.CSS_SELECTOR, 'div[data-testid="socialContext"]')
        if sc and any(e.is_displayed() for e in sc):
            return False
    except Exception:
        pass
    try:
        replying = article.find_elements(By.XPATH, './/*[contains(text(),"Replying to")]')
        if replying:
            return False
    except Exception:
        pass
    try:
        quoted = article.find_elements(By.CSS_SELECTOR, 'div[data-testid="card.wrapper"], article article')
        if quoted:
            return False
    except Exception:
        pass
    return True
# -----------------------------------------
def open_live_search(driver: webdriver.Chrome, query: str):
    q = f'{query} -filter:replies -filter:retweets -filter:quotes'
    url = f"https://x.com/search?q={quote_plus(q)}&src=typed_query&f=live"
    driver.get(url)
    WebDriverWait(driver, 20).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, 'main[role="main"]'))
    )
    jsleep(WAIT_LONG)
def open_creator_latest_search(driver: webdriver.Chrome, handle: str, query: str):
    """
    Opens Latest tab for: from:<handle> <query> excluding replies/retweets/quotes.
    """
    q = f'from:{handle} {query} -filter:replies -filter:retweets -filter:quotes'
    url = f"https://x.com/search?q={quote_plus(q)}&src=typed_query&f=live"
    driver.get(url)
    WebDriverWait(driver, 20).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, 'main[role="main"]'))
    )
    jsleep(WAIT_LONG)
def extract_handle_from_article(article) -> Optional[str]:
    try:
        name_block = article.find_element(By.CSS_SELECTOR, 'div[data-testid="User-Name"]')
        link = name_block.find_element(By.CSS_SELECTOR, 'a[href^="/"][role="link"]')
        href = link.get_attribute("href")
        if href and "x.com/" in href:
            handle = href.split("x.com/")[-1].split("?")[0].split("/")[0].strip()
            return handle
    except Exception:
        pass
    try:
        spans = article.find_elements(By.CSS_SELECTOR, 'div[data-testid="User-Name"] span')
        for s in spans:
            t = s.text.strip()
            if t.startswith("@") and len(t) > 1:
                return t.lstrip("@")
    except Exception:
        pass
    return None
def extract_tweet_id_url_text(article) -> Optional['TweetCandidate']:
    try:
        link = article.find_element(By.XPATH, './/a[contains(@href, "/status/") and .//time]')
        href = link.get_attribute("href")
        if not href:
            return None
        tweet_id = href.split("/status/")[-1].split("?")[0]
        try:
            text_el = article.find_element(By.CSS_SELECTOR, 'div[data-testid="tweetText"]')
            text = text_el.text.strip()
        except Exception:
            text = ""
        handle = extract_handle_from_article(article) or ""
        return TweetCandidate(tweet_id=tweet_id, tweet_url=href, user_handle=handle, text=text)
    except Exception:
        return None
def find_latest_openledger_original_for_creator(driver: webdriver.Chrome, handle: str) -> Optional['TweetCandidate']:
    """
    On the 'Latest' search for from:<handle> OpenLedger, take the FIRST article that:
      - matches original-post heuristics
      - belongs to <handle>
    """
    attempts = 0
    target = handle.lower()
    while attempts < 6:
        articles = driver.find_elements(By.CSS_SELECTOR, 'article[role="article"]')
        for art in articles:
            cand = extract_tweet_id_url_text(art)
            if not cand:
                continue
            if cand.user_handle.lower() != target:
                continue
            if SEARCH_QUERY.lower() not in (cand.text or "").lower():
                continue
            if not is_original_post(art):
                continue
            return cand
        # scroll some (jittered) to load a bit more
        frac = random.uniform(SCROLL_MIN_FRACTION, SCROLL_MAX_FRACTION)
        driver.execute_script(f"window.scrollBy(0, document.body.scrollHeight * {frac});")
        jsleep(WAIT_MED)
        attempts += 1
    return None

def collect_global_latest_openledger(driver, max_needed: int, processed_ids: Set[str]) -> List['TweetCandidate']:
    """
    Search global Latest for 'OpenLedger' (no replies/retweets/quotes),
    return up to max_needed ORIGINAL posts, unique by creator.
    """
    open_live_search(driver, SEARCH_QUERY) # Use SEARCH_QUERY
    unique_by_creator = {} # Dictionary to store unique tweets by creator handle (lowercase)
    scroll_attempts = 0
    target_lower = SEARCH_QUERY.lower() # Use SEARCH_QUERY

    while len(unique_by_creator) < max_needed and scroll_attempts < 12:
        articles = driver.find_elements(By.CSS_SELECTOR, 'article[role="article"]')
        for art in articles:
            if not is_original_post(art):
                continue
            cand = extract_tweet_id_url_text(art)
            if not cand:
                continue
            if cand.text and target_lower not in cand.text.lower():
                continue
            if cand.tweet_id in processed_ids:
                continue
            if OWN_HANDLE and cand.user_handle and cand.user_handle.lower() == OWN_HANDLE.lower():
                continue
            if not cand.user_handle:
                continue

            # Ensure uniqueness by creator (using lowercase handle as key)
            key = cand.user_handle.lower()
            if key not in unique_by_creator: # Only add if we haven't seen this creator yet
                unique_by_creator[key] = cand

            # Early exit if we have enough results
            if len(unique_by_creator) >= max_needed:
                break

        # Scroll if we still need more results
        if len(unique_by_creator) < max_needed:
            frac = random.uniform(SCROLL_MIN_FRACTION, SCROLL_MAX_FRACTION)
            driver.execute_script(f"window.scrollBy(0, document.body.scrollHeight * {frac});")
            jsleep(WAIT_MED)
            scroll_attempts += 1
        else:
            # Break loop if we have collected enough tweets
            break

    # Return the list of unique tweets, limited to max_needed
    # This ensures GLOBAL_UNIQUE_CREATORS behavior as intended
    return list(unique_by_creator.values())[:max_needed]

def open_reply_composer_for_article(driver: webdriver.Chrome, article) -> bool:
    # Try multiple selectors for the reply button
    selectors = [
        'div[data-testid="reply"]', # Older selector?
        'button[data-testid="reply"]', # Newer selector
        '[data-testid="reply"]' # General selector
    ]
    for sel in selectors:
        try:
            btn = WebDriverWait(article, 6).until(EC.element_to_be_clickable((By.CSS_SELECTOR, sel)))
            driver.execute_script("arguments[0].scrollIntoView({block:'center'});", btn)
            time.sleep(random.uniform(0.1, 0.25))
            try:
                btn.click()
            except Exception:
                driver.execute_script("arguments[0].click();", btn)
            return True
        except Exception:
            continue # Try the next selector if this one fails
    return False # All selectors failed

def post_reply(driver, text: str) -> bool:
    def _try_once():
        # Prioritize finding the textarea within the reply dialog/modal
        sel_textareas = [
            'div[role="dialog"] div[data-testid="tweetTextarea_0"]', # Within dialog
            'div[role="dialog"] div[contenteditable="true"][data-testid="tweetTextarea_0"]', # Specific contenteditable within dialog
            'div[data-testid="tweetTextarea_0"]', # General fallback
            'div[role="textbox"][data-testid="tweetTextarea_0"]' # Another potential fallback
        ]
        textarea = None
        for sel in sel_textareas:
            try:
                textarea = WebDriverWait(driver, 8).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, sel))
                )
                if textarea:
                    break # Found a textarea, exit the loop
            except Exception:
                pass # Try the next selector
        if not textarea:
            print("[!] Could not find reply textarea.")
            return False # Failed to find textarea

        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", textarea)
        time.sleep(random.uniform(0.1, 0.25))
        try:
            textarea.click()
        except Exception:
            driver.execute_script("arguments[0].click();", textarea)

        # human typing
        send_keys_human_enhanced(driver, text)

        # Prioritize finding the Post button within the reply dialog/modal
        post_selectors = [
            'div[role="dialog"] div[data-testid="tweetButton"]', # Within dialog
            'div[role="dialog"] button[data-testid="tweetButton"]', # Specific button within dialog
            'div[data-testid="tweetButton"]', # General fallback
            'button[data-testid="tweetButton"]' # Another general fallback
        ]
        for sel in post_selectors:
            try:
                post_btn = WebDriverWait(driver, 8).until(
                    EC.element_to_be_clickable((By.CSS_SELECTOR, sel))
                )
                driver.execute_script("arguments[0].scrollIntoView({block:'center'});", post_btn)
                time.sleep(random.uniform(0.1, 0.2))
                try:
                    post_btn.click()
                except Exception:
                    driver.execute_script("arguments[0].click();", post_btn)
                jsleep(1.2, 0.3)
                return True # Success
            except Exception:
                continue # Try the next selector if this one fails
        print("[!] Could not find or click the Post button.")
        return False # Failed to find/click Post button
    # Attempt posting once
    if _try_once():
        return True
    # If it fails, wait a bit and try again
    jsleep(1.0, 0.2)
    return _try_once() # Retry once

def _plan_mix_counts(total: int, global_percent: int):
    """Return (global_quota, creators_quota) from total & percent."""
    gp = max(0, min(100, int(global_percent)))
    global_quota = round((gp / 100.0) * total)
    creators_quota = max(0, total - global_quota)
    return global_quota, creators_quota


def run():
    """
    # --- License Check ---
    if not LICENSE_KEY:
        print("[!] LICENSE_KEY not found in config.json. Please add your license key.")
        sys.exit(1) # Exit with error code
    print("[i] Checking license key...")
    # Perform the online validation (this function is from license_check.py)
    validation_result = license_check.validate_license_online(
        license_key=LICENSE_KEY,
        product_name="TwitterBot", # Match the product name expected by your server
        bot_version="v1"           # Match the version expected by your server
    )
    if not validation_result["valid"]:
        print(f"[!] License validation failed: {validation_result['message']}")
        print("[!] Exiting bot. Please ensure you have a valid license key, internet access, and the key is bound to this machine.")
        sys.exit(1) # Exit with error code
    else:
        print(f"[✓] License validation successful! Welcome {validation_result['username']} (Version: {validation_result['version']}).")
        """
    # --- End License Check ---
    driver = setup_driver()
    processed_ids = read_processed_ids(PROCESSED_LOG)

    start_time = datetime.datetime.now() # <-- Record start time
    # --- Real-time Title Update Helper ---
    def update_title_bar(replies_done, total_budget, global_done, creators_done, force_update=False):
        """Updates the console title bar with current progress and elapsed time."""
        nonlocal start_time # Access the start_time variable from the outer scope
        try:
            current_time = datetime.datetime.now()
            elapsed_time = current_time - start_time
            # Format elapsed time as HH:MM:SS
            hours, remainder = divmod(int(elapsed_time.total_seconds()), 3600)
            minutes, seconds = divmod(remainder, 60)
            formatted_elapsed = f"{hours:02d}:{minutes:02d}:{seconds:02d}"

            # Create the title string
            title_text = f"Replies: {replies_done}/{total_budget} | Elapsed: {formatted_elapsed} | Global:{global_done}/Creators:{creators_done}"
            
            # Update the console window title (works on Windows with 'title' command)
            # Enclose in double quotes to handle spaces and special characters
            os.system(f'title "{title_text}"')
            
            # Optional: Print to console for debugging (uncomment if needed)
            # print(f"\r[Title Update] {title_text}", end='', flush=True) 
            
        except Exception as e:
            # Silently fail on title update errors to avoid disrupting the main flow
            # print(f"[!] Failed to update title bar: {e}") # Uncomment for debugging
            pass

    # --- End Title Update Helper ---

    try:
        cookies = load_cookies_from_file(COOKIE_FILE)
        inject_cookies(driver, cookies)
        jsleep(WAIT_LONG)
        ensure_logged_in(driver)
        total_budget = MAX_REPLIES_PER_RUN
        if ENABLE_MIX_MODE:
            global_quota, creators_quota = _plan_mix_counts(total_budget, MIX_GLOBAL_PERCENT)
        else:
            global_quota, creators_quota = 0, total_budget
        # Pre-build creator list (random order) for creator quota
        creators_all = [h.strip().lstrip("@") for h in CREATOR_USERNAMES if h.strip()]
        random.shuffle(creators_all)
        # --- Long pause injection state (feature #7) ---
        targets_since_pause = 0
        next_long_pause_after = random.randint(*LONG_PAUSE_EVERY_RANGE)
        print(f"[i] Long-pause will trigger after ~{next_long_pause_after} targets (first window).")
        replies_done = 0
        global_done = 0
        creators_done = 0
        creator_index = 0

          # --- Initial Title Update ---
        update_title_bar(replies_done, total_budget, global_done, creators_done, force_update=True)

        def cooldown_between_targets():
            # short, natural pause between targets (creator or global)
            sleep_time = random.uniform(5.0, 15.0)
            print(f"[i] Cooling down before next targetm: {sleep_time:.1f} sec")
            time.sleep(sleep_time)
        def maybe_long_pause():
            nonlocal targets_since_pause, next_long_pause_after
            if ENABLE_LONG_PAUSE:
                targets_since_pause += 1
                if targets_since_pause >= next_long_pause_after:
                    long_sleep = random.uniform(*LONG_PAUSE_DURATION_RANGE)
                    m, s = divmod(int(long_sleep), 60)
                    print(f"[i] Taking a long human break: ~{m}m {s}s (after {targets_since_pause} targets).")
                    time.sleep(long_sleep)
                    targets_since_pause = 0
                    next_long_pause_after = random.randint(*LONG_PAUSE_EVERY_RANGE)
                    print(f"[i] Next long-pause window set to ~{next_long_pause_after} targets.")
        while replies_done < total_budget:

             # Decide source this turn (global vs creator), weighted by remaining quotas
            choices = []
            if global_done < global_quota:
                choices.append("global")
            if creators_done < creators_quota:
                choices.append("creator")
            if not choices:
                break # No more targets to process

            pick = random.choice(choices)

            # --- Creator path ---
            if pick == "creator":
                # Check if we have more creators to process
                if creator_index >= len(creators_all):
                    print("[i] No more creators available to meet creator quota.")
                    # Check if we can switch to global mode
                    if global_done < global_quota:
                        pick = "global" # Switch to global
                    else:
                        break # No more targets available, exit loop

                # If still on creator path (either we had one or just switched from exhausted creators)
                if pick == "creator":
                    handle = creators_all[creator_index]
                    creator_index += 1
                    if OWN_HANDLE and handle.lower() == OWN_HANDLE.lower():
                        maybe_long_pause()
                        cooldown_between_targets()
                        # Update title after skipping
                        update_title_bar(replies_done, total_budget, global_done, creators_done)
                        continue
                    print(f"[i] (Creators) Searching latest {SEARCH_QUERY} original for @{handle} ...") # Use SEARCH_QUERY
                    open_creator_latest_search(driver, handle, SEARCH_QUERY) # Use SEARCH_QUERY
                    cand = find_latest_openledger_original_for_creator(driver, handle)
                    if not cand:
                        print(f"[i] No original {SEARCH_QUERY} post found for @{handle}.") # Use SEARCH_QUERY
                        maybe_long_pause()
                        cooldown_between_targets()
                        # Update title after not finding a post
                        update_title_bar(replies_done, total_budget, global_done, creators_done)
                        continue
                    if cand.tweet_id in processed_ids:
                        print(f"[i] Already processed {cand.tweet_id} for @{handle}.")
                        maybe_long_pause()
                        cooldown_between_targets()
                        # Update title after skipping processed
                        update_title_bar(replies_done, total_budget, global_done, creators_done)
                        continue
                    # Add human-like decision logic
                    if should_skip_tweet(cand.text, cand.user_handle):
                        maybe_long_pause()
                        cooldown_between_targets()
                        # Update title after skipping tweet
                        update_title_bar(replies_done, total_budget, global_done, creators_done)
                        continue
                    # Guard on detail
                    driver.get(cand.tweet_url)
                    jsleep(WAIT_MED)
                    try:
                        article = WebDriverWait(driver, 12).until(
                            EC.presence_of_element_located(
                                (By.XPATH, f'//article[.//a[contains(@href,"/status/{cand.tweet_id}")]]')
                            )
                        )
                    except Exception:
                        print(f"[!] Could not load article for {cand.tweet_id} (@{handle}).")
                        maybe_long_pause()
                        cooldown_between_targets()
                        # Update title after failing to load article
                        update_title_bar(replies_done, total_budget, global_done, creators_done)
                        continue
                    if not is_original_post(article):
                        print(f"[i] Skipped {cand.tweet_id} (@{handle}) — looks like reply/quote/repost.")
                        maybe_long_pause()
                        cooldown_between_targets()
                        # Update title after skipping non-original
                        update_title_bar(replies_done, total_budget, global_done, creators_done)
                        continue
                    # Simulate human browsing occasionally
                    simulate_human_browsing(driver)
                    # Simulate reading time
                    read_time = simulate_reading_time(cand.text)
                    print(f"[i] Simulating reading time: {read_time:.1f}s")
                    time.sleep(read_time)
                    if not open_reply_composer_for_article(driver, article):
                        print(f"[!] Could not open reply composer for {cand.tweet_id} (@{handle}).")
                        maybe_long_pause()
                        cooldown_between_targets()
                        # Update title after failing to open composer
                        update_title_bar(replies_done, total_budget, global_done, creators_done)
                        continue
                    # Context-aware reply generation (now uses single key)
                    context = analyze_tweet_context(cand.text)
                    reply_text = generate_reply_with_gemini_enhanced(cand.text)
                    # Add human decision to skip reply
                    if should_skip_reply():
                        print(f"[i] Decided to skip replying to @{handle}")
                        maybe_long_pause()
                        cooldown_between_targets()
                        continue
                    if post_reply(driver, reply_text):
                        print(f"[✓] Replied to @{handle} ({cand.tweet_id}) -> {reply_text}")
                        append_processed_id(PROCESSED_LOG, cand.tweet_id)
                        processed_ids.add(cand.tweet_id)
                        replies_done += 1
                        creators_done += 1
                        # --- Add Engagement Features Here (Creator Path) (Fixed probabilities) ---
                        # Like the post (30% chance - Fixed for v1)
                        if should_like_reply():
                            print(f"[i] Attempting to like post {cand.tweet_id}...")
                            if not like_post(driver, article, cand.tweet_id): # Pass article and tweet_id
                                 print(f"[i] Like attempt for {cand.tweet_id} failed or skipped.")
                        # Follow the creator (2% chance - Fixed for v1)
                        if should_follow_creator():
                            print(f"[i] Attempting to follow @{handle}...")
                            if not follow_creator(driver, handle): # Pass handle
                                 print(f"[i] Follow attempt for @{handle} failed or skipped.")
                        # --- End Engagement Features ---
                        time.sleep(random.uniform(6.0, 14.0))  # reply cooldown
                    else:
                        print(f"[!] Failed to post reply for {cand.tweet_id} (@{handle}).")
                    maybe_long_pause()
                    cooldown_between_targets()

            # --- Global path ---
            if pick == "global": # Use if/elif/else or separate if for clarity, but this works with the re-evaluation logic above
                 remaining = global_quota - global_done
                 if remaining <= 0:
                     # This check might be redundant now due to the choices list logic, but kept for safety
                     maybe_long_pause()
                     cooldown_between_targets()
                     # Update title after skipping global due to quota
                     update_title_bar(replies_done, total_budget, global_done, creators_done)
                     continue
                 print(f"[i] (Global) Collecting latest {SEARCH_QUERY} originals (need up to {remaining}) ...") # Use SEARCH_QUERY
                 globals_batch = collect_global_latest_openledger(driver, remaining, processed_ids)
                 if not globals_batch:
                     print("[i] No suitable global posts found right now.")
                     maybe_long_pause()
                     cooldown_between_targets()
                     # Update title after finding no global posts
                     update_title_bar(replies_done, total_budget, global_done, creators_done)
                     continue
                 # Randomize batch order slightly
                 random.shuffle(globals_batch)
                 for cand in globals_batch:
                     if replies_done >= total_budget or global_done >= global_quota:
                         break
                     # Add human-like decision logic
                     if should_skip_tweet(cand.text, cand.user_handle):
                         # Update title after skipping tweet in batch
                         update_title_bar(replies_done, total_budget, global_done, creators_done)
                         continue # Skip to next candidate in the batch
                     # Double-guard on detail page
                     driver.get(cand.tweet_url)
                     jsleep(WAIT_MED)
                     try:
                         article = WebDriverWait(driver, 12).until(
                             EC.presence_of_element_located(
                                 (By.XPATH, f'//article[.//a[contains(@href,"/status/{cand.tweet_id}")]]')
                             )
                         )
                     except Exception:
                         print(f"[!] Could not load article for {cand.tweet_id} (@{cand.user_handle}).")
                         # Update title after failing to load article in batch
                         update_title_bar(replies_done, total_budget, global_done, creators_done)
                         continue # Skip to next candidate in the batch
                     if not is_original_post(article):
                         print(f"[i] Skipped {cand.tweet_id} (@{cand.user_handle}) — looks like reply/quote/repost.")
                         # Update title after skipping non-original in batch
                         update_title_bar(replies_done, total_budget, global_done, creators_done)
                         continue # Skip to next candidate in the batch
                     # Simulate human browsing occasionally
                     simulate_human_browsing(driver)
                     # Simulate reading time
                     read_time = simulate_reading_time(cand.text)
                     print(f"[i] Simulating reading time: {read_time:.1f}s")
                     time.sleep(read_time)
                     if not open_reply_composer_for_article(driver, article):
                         print(f"[!] Could not open reply composer for {cand.tweet_id} (@{cand.user_handle}).")
                         # Update title after failing to open composer in batch
                         update_title_bar(replies_done, total_budget, global_done, creators_done)
                         continue # Skip to next candidate in the batch
                     # Context-aware reply generation (now uses single key)
                     context = analyze_tweet_context(cand.text)
                     reply_text = generate_reply_with_gemini_enhanced(cand.text)
                     # Add human decision to skip reply
                     if should_skip_reply():
                         print(f"[i] Decided to skip replying to @{cand.user_handle}")
                         update_title_bar(replies_done, total_budget, global_done, creators_done)
                         continue # Skip to next candidate in the batch
                     if post_reply(driver, reply_text):
                         print(f"[✓] Replied to @{cand.user_handle} ({cand.tweet_id}) -> {reply_text}")
                         append_processed_id(PROCESSED_LOG, cand.tweet_id)
                         processed_ids.add(cand.tweet_id)
                         replies_done += 1
                         global_done += 1

                         # --- REAL-TIME TITLE UPDATE ON SUCCESS ---
                         update_title_bar(replies_done, total_budget, global_done, creators_done, force_update=True)
                         # --- End Real-time Update ---

                         # --- Add Engagement Features Here (Global Path) (Fixed probabilities) ---
                         # Like the post (30% chance - Fixed for v1)
                         if should_like_reply():
                             print(f"[i] Attempting to like post {cand.tweet_id}...")
                             # We are on the tweet detail page
                             if not like_post(driver, article, cand.tweet_id): # Pass article and tweet_id
                                  print(f"[i] Like attempt for {cand.tweet_id} failed or skipped.")
                         # Follow the creator (2% chance - Fixed for v1)
                         if should_follow_creator():
                             print(f"[i] Attempting to follow @{cand.user_handle}...")
                             if not follow_creator(driver, cand.user_handle): # Pass handle
                                  print(f"[i] Follow attempt for @{cand.user_handle} failed or skipped.")
                         # --- End Engagement Features ---
                         time.sleep(random.uniform(6.0, 14.0))  # reply cooldown
                     else:
                         print(f"[!] Failed to post reply for {cand.tweet_id} (@{cand.user_handle}).")
                 maybe_long_pause()
                 cooldown_between_targets() # Cooldown after processing the global batch


        # # --- Update Title One Final Time at the End ---
        #     end_time = datetime.datetime.now()
        #     total_elapsed = end_time - start_time
        #     hours, remainder = divmod(int(total_elapsed.total_seconds()), 3600)
        #     minutes, seconds = divmod(remainder, 60)
        #     formatted_total_elapsed = f"{hours:02d}:{minutes:02d}:{seconds:02d}"
        #     final_title_text = f"Run Complete | Total Replies: {replies_done}/{total_budget} | Total Time: {formatted_total_elapsed}"
            # os.system(f'title "{final_title_text}"')

        # --- Update Title One Final Time at the End ---
        end_time = datetime.datetime.now()
        total_elapsed = end_time - start_time
        hours, remainder = divmod(int(total_elapsed.total_seconds()), 3600)
        minutes, seconds = divmod(remainder, 60)
        formatted_total_elapsed = f"{hours:02d}:{minutes:02d}:{seconds:02d}"
        final_title_text = f"Run Complete | Total Replies: {replies_done}/{total_budget} | Total Time: {formatted_total_elapsed}"
        os.system(f'title "{final_title_text}"')
        save_refreshed_cookies(driver, COOKIE_FILE)
        print(f"[i] Done. Replies this run: {replies_done}/{MAX_REPLIES_PER_RUN} "
              f"(global: {global_done}, creators: {creators_done})"
              f"Total Time Taken: {formatted_total_elapsed}")

    finally:
        # Optional: Reset title on exit?
        # os.system(f'title Command Prompt') # Or just leave the final status
        try:
            driver.quit()
        except Exception:
            pass
if __name__ == "__main__":
    run()
