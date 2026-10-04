#!/usr/bin/env python3
"""
HR CASINO — fair-play game bot
- Choose: vs Bot OR PvP
- Both sides send emoji
- CRAZY = lower points wins
Group: -1003988142532
"""

import asyncio
import json
import logging
import os
import secrets
import string
import time
from datetime import datetime, date
from pathlib import Path
from typing import Dict, Any, Set, Optional

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand, BotCommandScopeAllGroupChats, BotCommandScopeAllPrivateChats, InputFile, MessageEntity
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters,
)
from telegram.request import HTTPXRequest

BOT_TOKEN = os.environ.get("BOT_TOKEN", "8656379534:AAHwegXduTh3Fdf7ci2qImBanTTB9eg__T0").strip()
OWNER_IDS: Set[int] = {8314045587}
PAYMENT_CHANNEL_ID = -1004425304005
GROUP_ID = -1003922946692  # HR Casino group
# Wins logger channel (AxomCasino Wins style). Bot must be ADMIN of this channel.
# Set via env WINS_CHANNEL_ID or /setwinschannel -100xxxxxxxxxx
WINS_CHANNEL_ID = int(os.environ.get("WINS_CHANNEL_ID", "0") or 0)
GROUP_LINK = "https://t.me/+YOUR_INVITE_HASH"  # apna group invite link yahan
UPI_ID = os.environ.get("UPI_ID", "").strip()
UPI_NAME = os.environ.get("UPI_NAME", "").strip()
# Binance auto-deposit (set SECRET in env for live auto-credit)
BINANCE_API_KEY = os.environ.get("BINANCE_API_KEY", "IW4t8d5rDw8iBfATGWekOGGUj7gLLSf0egXEqWq4imQdDUT3gM50qW5MolPQliBC").strip()
BINANCE_API_SECRET = os.environ.get("BINANCE_API_SECRET", "").strip()
BINANCE_DEPOSIT_COIN = os.environ.get("BINANCE_DEPOSIT_COIN", "USDT").strip()
BINANCE_DEPOSIT_NETWORK = os.environ.get("BINANCE_DEPOSIT_NETWORK", "TRX").strip()  # TRC20
# GPay.one merchant (portal: https://mch.gpay.one/) — change password in portal!
GPAY_MERCHANT_ID = os.environ.get("GPAY_MERCHANT_ID", "A801").strip()
GPAY_MERCHANT_PASS = os.environ.get("GPAY_MERCHANT_PASS", "1072907e69").strip()
GPAY_API_BASE = os.environ.get("GPAY_API_BASE", "https://api.gpay.one").strip()
GPAY_PORTAL = "https://mch.gpay.one/"
SUPPORT_USER = "Hrcasinosupport"
SUPPORT_PAY = "Hrcasinosupport"
SUPPORT_GAMES = "Hrcasinosupport"
GROUP_NAME = "HR Casino"

CURRENCIES = [
    "USD", "INR", "EUR", "GBP", "AED", "BDT", "PKR",
    "CAD", "AUD", "SGD", "PHP", "IDR", "BRL", "TRY",
]
# display rates vs INR (approx; admin can /setrate)
DEFAULT_RATES = {
    "INR": 1.0, "USD": 84.0, "EUR": 91.0, "GBP": 106.0, "AED": 23.0,
    "BDT": 0.70, "PKR": 0.30, "CAD": 62.0, "AUD": 55.0, "SGD": 63.0,
    "PHP": 1.5, "IDR": 0.0052, "BRL": 15.0, "TRY": 2.5,
}
# Deposit addresses (from owner wallet list)
CRYPTO_WALLETS = {
    "BTC": "bc1q04eyrg4lhdev7f2lrpart5x9fch9yt5zt5axne",
    "ETH": "0x879F32367B0c6a142D6E8081619869A40A029a45",
    "USDT_ERC20": "0x879F32367B0c6a142D6E8081619869A40A029a45",
    "USDT_TRC20": "TNLJw6eEjJw4Cy9uFCUegLyi9ZRLXi9uAp",
    "TRX": "TNLJw6eEjJw4Cy9uFCUegLyi9ZRLXi9uAp",
    "USDT_BEP20": "0x879F32367B0c6a142D6E8081619869A40A029a45",
    "BNB": "0x879F32367B0c6a142D6E8081619869A40A029a45",
    "BEP20": "0x879F32367B0c6a142D6E8081619869A40A029a45",
    "POLYGON": "0x879F32367B0c6a142D6E8081619869A40A029a45",
    "USDT_POLYGON": "0x879F32367B0c6a142D6E8081619869A40A029a45",
    "ARBITRUM": "0x879F32367B0c6a142D6E8081619869A40A029a45",
    "SOL": "2JNAR9z71YnTaorFaYGh9id6FoNjhJ1ri1HYuxLedXrU",
    "USDT_SOL": "2JNAR9z71YnTaorFaYGh9id6FoNjhJ1ri1HYuxLedXrU",
    "TON": "EQAj7vKLbaWjaNbAuAKP1e1HwmdYZ2vJ2xtWU8qq3JafkfxF",
    "USDT_TON": "EQAj7vKLbaWjaNbAuAKP1e1HwmdYZ2vJ2xtWU8qq3JafkfxF",
}
CRYPTO_MEMOS = {
    "TON": "1485263",
    "USDT_TON": "1485263",
}
MIN_WITHDRAW_CRYPTO = 5.0  # USDT
REFERRAL_BONUS = 10          # flat ₹ on referred user's 1st deposit
REFERRAL_DEPOSIT_PCT = 0.20  # 20% of deposit to referrer
MIN_BET = 300
MAX_BET = 300
MIN_DEPOSIT = 300
MIN_WITHDRAW = 150
HOUSE_TAX = 0.04  # Disclose this fee anywhere it affects payouts.

def unique_deposit_amount(base: float, user_id: int) -> float:
    """Attach unique paisa so owner can match UPI credit (pseudo auto-verify)."""
    # e.g. 300 + (uid % 90 + 10)/100 → 300.10 .. 300.99
    paisa = (int(user_id) % 90) + 10
    return round(float(base) + paisa / 100.0, 2)


import hashlib
import hmac
import urllib.parse

try:
    import httpx
except Exception:
    httpx = None


def _binance_sign(params: dict, secret: str) -> str:
    qs = urllib.parse.urlencode(params)
    return hmac.new(secret.encode(), qs.encode(), hashlib.sha256).hexdigest()


async def binance_deposit_address(coin: str = None, network: str = None):
    """Fetch deposit address from Binance (needs API key + secret with enable reading)."""
    coin = coin or BINANCE_DEPOSIT_COIN
    network = network or BINANCE_DEPOSIT_NETWORK
    if not BINANCE_API_KEY or not BINANCE_API_SECRET or not httpx:
        return None
    params = {"coin": coin, "timestamp": int(time.time() * 1000)}
    if network:
        params["network"] = network
    params["signature"] = _binance_sign(params, BINANCE_API_SECRET)
    headers = {"X-MBX-APIKEY": BINANCE_API_KEY}
    url = "https://api.binance.com/sapi/v1/capital/deposit/address"
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            r = await client.get(url, params=params, headers=headers)
            if r.status_code == 200:
                return r.json()
            return {"error": r.text, "status": r.status_code}
    except Exception as e:
        return {"error": str(e)}


async def binance_recent_deposits(coin: str = None, limit: int = 20):
    if not BINANCE_API_KEY or not BINANCE_API_SECRET or not httpx:
        return []
    coin = coin or BINANCE_DEPOSIT_COIN
    params = {"coin": coin, "limit": limit, "timestamp": int(time.time() * 1000)}
    params["signature"] = _binance_sign(params, BINANCE_API_SECRET)
    headers = {"X-MBX-APIKEY": BINANCE_API_KEY}
    url = "https://api.binance.com/sapi/v1/capital/deposit/hisrec"
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            r = await client.get(url, params=params, headers=headers)
            if r.status_code == 200:
                return r.json() if isinstance(r.json(), list) else []
            return []
    except Exception:
        return []


def build_bot_vals_for_total(uvals, rule: str, player_wins: bool, lo: int, hi: int):
    """Generate independent bot values without targeting a winner."""
    del rule, player_wins
    n = max(1, len(uvals))
    span = max(1, int(hi) - int(lo) + 1)
    return [int(lo) + secrets.randbelow(span) for _ in range(n)]



def emoji_value_range(emoji: str):
    """Telegram dice value ranges for all emoji games."""
    if emoji in ("🏀", "⚽"):
        return 1, 5
    if emoji == "🎰":
        return 1, 64
    # 🎲 🎯 🎳 all 1-6
    return 1, 6


def fair_bot_value(user_val: int, rule: str, player_win_rate: float, lo: int = 1, hi: int = 6) -> int:
    """Return a fresh, unbiased value without examining the player's roll."""
    del user_val, rule, player_win_rate
    return int(lo) + secrets.randbelow(max(1, int(hi) - int(lo) + 1))


def round_winner(uv: int, bv: int, rule: str) -> str:
    """Return 'user' | 'bot' | 'tie' from scores. Honest — no flip."""
    if uv == bv:
        return "tie"
    if (rule or "normal").lower() == "crazy":
        return "user" if uv < bv else "bot"
    return "user" if uv > bv else "bot"


def total_winner(user_total: int, bot_total: int, rule: str) -> str:
    """Summed points: normal = higher wins, crazy = lower wins."""
    if int(user_total) == int(bot_total):
        return "tie"
    if (rule or "normal").lower() == "crazy":
        return "user" if int(user_total) < int(bot_total) else "bot"
    return "user" if int(user_total) > int(bot_total) else "bot"


def style_btn(text, style=None, **kwargs):
    """Safe buttons — NO style= (breaks some hosts / API). Unicode icons only.
    Telegram does not support custom premium emoji IDs on button labels.
    """
    kwargs.pop("style", None)  # never pass style to InlineKeyboardButton
    st = style
    t = str(text).strip()
    for p in ("✅ ", "❌ ", "🔵 ", "🟢 ", "🔴 ", "✔️ ", "⬅️ ", "➡️ "):
        if t.startswith(p):
            t = t[len(p):].strip()
            break
    has_icon = bool(t) and (ord(t[0]) > 0x2000 or t[0] in "✅❌⭐🔥💰🎲💳")
    if st == "success" and not has_icon:
        t = "✅ " + t
    elif st == "danger" and not has_icon:
        t = "❌ " + t
    elif st == "primary" and not has_icon:
        t = "🔹 " + t
    # Only standard kwargs: text, callback_data, url, etc.
    safe = {}
    for k in ("callback_data", "url", "switch_inline_query", "switch_inline_query_current_chat",
              "web_app", "login_url", "pay", "callback_game"):
        if k in kwargs:
            safe[k] = kwargs[k]
    return InlineKeyboardButton(t, **safe)



# ----- Premium emoji (MessageEntity method — same as like bot) -----
# Like bot jaisa: HTML nahi, entities se custom_emoji_id

def rolex_main_kb(me_username: str = None):
    """Rolex-style menu — plain InlineKeyboardButton only (no style=, no tg://)."""
    B = InlineKeyboardButton
    dep = f"https://t.me/{me_username}?start=deposit" if me_username else None
    wd = f"https://t.me/{me_username}?start=withdraw" if me_username else None
    if dep:
        row_dep = [B("💰 Deposit", url=dep), B("🚀 Withdraw", url=wd or dep)]
    else:
        row_dep = [
            B("💰 Deposit", callback_data="menu_deposit"),
            B("🚀 Withdraw", callback_data="menu_withdraw"),
        ]
    support_url = f"https://t.me/{SUPPORT_PAY}" if SUPPORT_PAY else None
    support_btn = (
        B("📣 Support", url=support_url)
        if support_url
        else B("📣 Support", callback_data="menu_help")
    )
    return InlineKeyboardMarkup([
        [B("💰 Wallet", callback_data="menu_wallet"), B("👤 Profile", callback_data="menu_stats")],
        [B("🎲 Games", callback_data="menu_games"), B("🧾 History", callback_data="menu_history")],
        row_dep,
        [B("💳 Set Wallet", callback_data="menu_setwallet")],
        [B("💱 Currency", callback_data="menu_currency"), B("🌐 Language", callback_data="menu_lang")],
        [support_btn, B("🎉 Giveaways", callback_data="menu_jackpot")],
        [B("📖 How to play", callback_data="menu_help"), B("📜 Terms", callback_data="menu_rules")],
    ])


CUSTOM_EMOJIS = {
    # Premium custom emoji IDs from user packs (CARDERS / Furion / CatPaws / youthAdaptive / FF)
    "ok": ("✅", "6089418114171147667"),
    "check": ("✅", "6325426068870143199"),
    "cross": ("❌", "6325351267719716133"),
    "warn": ("⚠️", "6089079808187174973"),
    "fire": ("🔥", "6325759792124009011"),
    "fire2": ("🔥", "6086954744268460848"),
    "money": ("💰", "6089104607328342288"),
    "money2": ("💰", "6325806800541063550"),
    "cash": ("💵", "6327872207364038132"),
    "bag": ("💰", "5303159080020372094"),
    "bank": ("🏦", "5431656757690667949"),
    "crown": ("👑", "6089003761496232797"),
    "crown2": ("👑", "6325457246037744649"),
    "gift": ("🎁", "6325574249536822079"),
    "gift2": ("🎁", "5384578448633129482"),
    "trophy": ("🏆", "5413566144986503832"),
    "star": ("⭐", "6339056030133289208"),
    "star2": ("🌟", "6086924086791902713"),
    "diamond": ("💎", "6086778246882399112"),
    "diamond2": ("💎", "6328045328905805342"),
    "coin": ("🪙", "5371009929685525704"),
    "coin2": ("🪙", "6327983502851577930"),
    "rocket": ("🚀", "6325647693477583541"),
    "chart": ("📊", "6325755651775535595"),
    "user": ("👤", "4945047803551286330"),
    "handshake": ("🤝", "6086990448331592466"),
    "heart": ("❤️‍🔥", "6089028758205897441"),
    "broken": ("💔", "6088971480522035863"),
    "dice": ("🎲", "5350460637182993292"),
    "target": ("🎯", "5350460637182993292"),
    "slot_e": ("🎰", "5350460637182993292"),
    "game": ("🎮", "5283006659675858301"),
    "bot": ("🤖", "4944968432555656092"),
    "robot": ("🤖", "4944968432555656092"),
    "person": ("👤", "4945047803551286330"),
    "win": ("🏆", "5413566144986503832"),
    "lose": ("💔", "6088971480522035863"),
    "bell": ("🔔", "6325335870261958398"),
    "chat": ("💬", "5386691718571646404"),
    "globe": ("🌐", "6285048454255220485"),
    "promo": ("🎟️", "5368756703942706282"),
    "new": ("🆕", "5424739631256081158"),
    "block": ("🚫", "6086741365998227951"),
    "plus": ("➕", "6093406373557571574"),
    "minus": ("➖", "5429398124584014630"),
    "rich": ("🤑", "5386757680679377085"),
    "sad": ("😭", "6093930033150170743"),
    "devil": ("😈", "5303432841235819631"),
    "sword": ("⚔️", "5368610511845886263"),
    "refresh": ("🔄", "5375338737028841420"),
    "time": ("⏰", "5386415655253730366"),
    "gold": ("🥇", "5345775424863509963"),
    "card": ("💳", "5339421025044035687"),
    "bomb": ("💣", "6325615391028551881"),
    "pin": ("📌", "6325862832684407546"),
    "top": ("🔝", "6086784182527202100"),
    "spark": ("✨", "6325336377068100031"),
    "zap": ("⚡", "6325529358538644192"),
    "mega": ("📣", "6325409576195725840"),
    "party": ("🎉", "6267117038808870117"),
    "thumb": ("👍", "6089313931149448495"),
    "eyes": ("👀", "6325758520813688968"),
    "lock": ("🔒", "6282846669335702032"),
    "key": ("🔑", "5413395871008058098"),
    "camera": ("📸", "5370607250731718891"),
    "link": ("🔗", "5305525533986027147"),
    "shield": ("🛡", "6325354871197277589"),
    "dollar": ("💲", "6089140105233044310"),
    "spend": ("💸", "6086730718774300509"),
    "dice2": ("🎲", "5350460637182993292"),
}

PREMIUM_POOL = [
    "6089104607328342288", "6325806800541063550", "5303159080020372094",
    "6089418114171147667", "6325426068870143199", "6089003761496232797",
    "6325457246037744649", "6325759792124009011", "6086954744268460848",
    "6325574249536822079", "5413566144986503832", "6086778246882399112",
    "6328045328905805342", "5371009929685525704", "6327983502851577930",
    "6325335870261958398", "6325529358538644192", "6325336377068100031",
    "6086990448331592466", "6089028758205897441", "5283006659675858301",
    "5431656757690667949", "5386757680679377085", "6327872207364038132",
]

# @Dices / RDices pack — roulette spin (random each play)
ROULETTE_EMOJI_IDS = [
    "5873171256756410604", "5872815758018353147", "5873062134522321185",
    "5872738787909441810", "5873207832697904393", "5872975676830653116",
    "5872985310442296591", "5873084399632783110", "5872946277779511562",
    "5872888626433496985", "5873093071171755531", "5870793618695919250",
    "5872854640357283482", "5872821135317408164", "5872907648843651336",
    "5872908739765344390", "5872729695463675868", "5872791345424243465",
    "5870902998628046689", "5873195248443725633", "5872968444105726614",
    "5870456751525991988", "5873199685144942388", "5873032018211640401",
    "5873009628547128179", "5872889652930681343", "5872998014955558245",
    "5872749873220034118", "5870564503665514704", "5872983725599364721",
    "5873094381136779410", "5873151547151489518", "5872956843399059712",
    "5873030811325830935", "5870868411256413003", "5870866761988971422",
    "5873034105565747010", "5873088819154130848",
]

def ce(key: str, fallback: str = "✨") -> str:
    """Plain char only (entities added by reply_prem)."""
    char, _ = CUSTOM_EMOJIS.get(key, (fallback, None))
    return char

def _utf16_len(s: str) -> int:
    return len(s.encode("utf-16-le")) // 2

def build_prem(parts) -> tuple:
    """
    parts: list of str or ("key",) tuples for premium emoji
    returns (text, entities)
    """
    text_out = ""
    entities = []
    for p in parts:
        if isinstance(p, tuple):
            key = p[0]
            char, eid = CUSTOM_EMOJIS.get(key, ("✨", None))
            if not eid and PREMIUM_POOL:
                eid = secrets.choice(PREMIUM_POOL)
            off = _utf16_len(text_out)
            text_out += char
            if eid:
                entities.append(MessageEntity(
                    type="custom_emoji",
                    offset=off,
                    length=_utf16_len(char),
                    custom_emoji_id=str(eid),
                ))
        else:
            text_out += str(p)
    return text_out, entities


async def reply_box(message, title: str, lines: list, footer: str = "", reply_markup=None):
    """Axom/BV style: title + blockquote box + footer (HTML)."""
    box = "\n".join(str(x) for x in lines)
    text_html = f"<b>{title}</b>\n\n<blockquote>{box}</blockquote>"
    if footer:
        text_html += f"\n\n{footer}"
    try:
        await message.reply_text(text_html, parse_mode="HTML", reply_markup=reply_markup)
    except Exception:
        plain = f"{title}\n\n" + "\n".join(str(x) for x in lines) + (("\n\n" + footer) if footer else "")
        await message.reply_text(plain, reply_markup=reply_markup)

async def reply_prem(message, parts, reply_markup=None, **kw):
    """Send with premium emoji entities only (no HTML)."""
    txt, ents = build_prem(parts)
    try:
        return await message.reply_text(txt, entities=ents, reply_markup=reply_markup, **kw)
    except Exception as e:
        logger.warning("prem send failed %s — fallback", e)
        return await message.reply_text(txt, reply_markup=reply_markup, **kw)

async def edit_prem(message, parts, reply_markup=None, **kw):
    txt, ents = build_prem(parts)
    try:
        return await message.edit_text(txt, entities=ents, reply_markup=reply_markup, **kw)
    except Exception as e:
        logger.warning("prem edit failed %s", e)
        try:
            return await message.edit_text(txt, reply_markup=reply_markup, **kw)
        except Exception:
            return None

async def photo_prem(message, photo, parts, reply_markup=None):
    txt, ents = build_prem(parts)
    try:
        return await message.reply_photo(photo=photo, caption=txt, caption_entities=ents, reply_markup=reply_markup)
    except Exception as e:
        logger.warning("prem photo %s", e)
        try:
            return await message.reply_photo(photo=photo, caption=txt, reply_markup=reply_markup)
        except Exception:
            return await reply_prem(message, parts, reply_markup=reply_markup)



DATA_FILE = str(Path(__file__).with_name("bet_bot_data.json"))
PENDING_TIMEOUT = 120

# ----- File logs (logs/ next to this script) -----
_LOG_DIR = Path(__file__).resolve().parent / "logs"
try:
    _LOG_DIR.mkdir(parents=True, exist_ok=True)
except Exception:
    pass
_fmt = logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s")
logging.basicConfig(format="%(asctime)s %(levelname)s %(message)s", level=logging.INFO)
logger = logging.getLogger("hrcasino")
logger.setLevel(logging.INFO)


def _ensure_file_logger(name: str, filename: str, propagate: bool = False):
    lg = logging.getLogger(name)
    lg.setLevel(logging.INFO)
    lg.propagate = propagate
    if not any(isinstance(h, logging.FileHandler) for h in lg.handlers):
        try:
            h = logging.FileHandler(_LOG_DIR / filename, encoding="utf-8")
            h.setFormatter(_fmt)
            lg.addHandler(h)
        except Exception:
            pass
    return lg


if not any(isinstance(h, logging.FileHandler) for h in logger.handlers):
    try:
        _fh = logging.FileHandler(_LOG_DIR / "hrcasino.log", encoding="utf-8")
        _fh.setFormatter(_fmt)
        logger.addHandler(_fh)
    except Exception:
        pass

dep_log = _ensure_file_logger("hrcasino.deposits", "deposits.log")
game_log = _ensure_file_logger("hrcasino.games", "games.log")
admin_log = _ensure_file_logger("hrcasino.admin", "admin.log")


def log_deposit(user_id, method: str, amount, extra: str = ""):
    dep_log.info("uid=%s method=%s amount=%s %s", user_id, method, amount, extra)


def log_game(user_id, game: str, stake, result: str, extra: str = ""):
    game_log.info("uid=%s game=%s stake=%s result=%s %s", user_id, game, stake, result, extra)


def log_admin(actor_id, action: str, extra: str = ""):
    admin_log.info("admin=%s action=%s %s", actor_id, action, extra)


# game key -> (emoji, label)
GAMES = {
    "dice": ("🎲", "Dice"),
    "basket": ("🏀", "Basket"),
    "football": ("⚽", "Football"),
    "bowl": ("🎳", "Bowl"),
    "dart": ("🎯", "Dart"),
    "slot": ("🎰", "Slot"),
    "coin": ("🪙", "Coin Flip"),
}


def default_data():
    return {
        "users": {},
        "pending_pay": {},
        "pending_bets": {},
        "allowed_groups": [],
        "bj": {},  # uid -> waiting emoji (solo vs bot)
        "pvp": {},  # pid -> pvp match state
        "bets": [],
        "banned": [],
        "bot_admins": [],  # can change name branding only

        "custom_games": {},
        "settings": {
            "upi": UPI_ID,
            "upi_name": UPI_NAME,
            "payment_channel": PAYMENT_CHANNEL_ID,
            "group_id": -1003922946692,
            "referral_bonus": REFERRAL_BONUS,
            "min_bet": MIN_BET,
            "min_deposit": MIN_DEPOSIT,
            "bot_on": True,
            "disabled_games": [],
            "max_bet": MAX_BET,
            "welcome_bonus": 0,
            "owners": list(OWNER_IDS),
            "group_name": GROUP_NAME,
        },
        "stats": {"bets": 0, "wagered": 0.0, "paid": 0.0, "deposits": 0},
        "jackpot_pool": 0.0,
    }


def load():
    if not Path(DATA_FILE).exists():
        d = default_data()
        save(d)
        return d
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            d = json.load(f)
        for k, v in default_data().items():
            d.setdefault(k, v)
        d.setdefault("settings", {})
        d["settings"]["max_bet"] = MAX_BET
        d["settings"].setdefault("bot_on", True)
        d["settings"].setdefault("disabled_games", [])
        d["settings"].setdefault("min_bet", MIN_BET)
        d["settings"].setdefault("min_deposit", MIN_DEPOSIT)
        d["settings"].setdefault("min_withdraw", MIN_WITHDRAW)
        d["settings"].setdefault("max_withdraw", 50000)
        d["settings"].setdefault("rig_mode", "off")
        d["settings"].setdefault("rates", dict(DEFAULT_RATES))
        return d
    except Exception:
        return default_data()


def save(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def owners(data) -> Set[int]:
    o = set(OWNER_IDS)
    for x in data.get("settings", {}).get("owners", []):
        try:
            o.add(int(x))
        except Exception:
            pass
    return o



def is_frozen(data, uid) -> bool:
    return str(uid) in (data.get("frozen") or {})


def bot_is_on(data) -> bool:
    return bool(data.get("settings", {}).get("bot_on", True))


def game_enabled(data, game_key: str) -> bool:
    off = data.get("settings", {}).get("disabled_games") or []
    return str(game_key).lower() not in [str(x).lower() for x in off]


def min_bet_val(data) -> float:
    try:
        return float(data.get("settings", {}).get("min_bet", MIN_BET))
    except Exception:
        return float(MIN_BET)


def min_dep_val(data) -> float:
    try:
        return float(data.get("settings", {}).get("min_deposit", MIN_DEPOSIT))
    except Exception:
        return float(MIN_DEPOSIT)


async def check_bot_and_game(update, context, data, game_key: str = None) -> bool:
    """Return False if bot/game off (and reply maintenance)."""
    user = update.effective_user
    if user and is_frozen(data, user.id):
        try:
            await update.effective_message.reply_text("🔒 Your wallet is frozen. Contact support.")
        except Exception:
            pass
        return False
    if not bot_is_on(data):
        try:
            await update.effective_message.reply_text(
                "🛠 <b>Bot under maintenance</b>\n\n"
                "<blockquote>Please wait — admin will turn it back on soon.</blockquote>",
                parse_mode="HTML",
            )
        except Exception:
            pass
        return False
    if game_key and not game_enabled(data, game_key):
        try:
            await update.effective_message.reply_text(
                f"🛠 <b>{game_key.upper()} under maintenance</b>\n\n"
                f"<blockquote>This game is temporarily disabled.\nTry another game.</blockquote>",
                parse_mode="HTML",
            )
        except Exception:
            pass
        return False
    return True


def is_owner(data, uid: int) -> bool:
    return uid in owners(data)


def is_banned(data, uid: int) -> bool:
    return str(uid) in data.get("banned", [])


def rid(prefix="X"):
    alphabet = string.ascii_uppercase + string.digits
    return prefix + "".join(secrets.choice(alphabet) for _ in range(6))


def ensure_user(data, user) -> dict:
    uid = str(user.id)
    users = data.setdefault("users", {})
    if uid not in users:
        users[uid] = {
            "balance": 0.0,
            "ref_code": rid("R"),
            "referred_by": None,
            "referrals": 0,
            "wagered": 0.0,
            "won": 0.0,
            "lost": 0.0,
            "bets": 0,
            "username": (user.username or "") if user else "",
            "name": (user.first_name or "") if user else "",
            "joined": str(date.today()),
        }
        save(data)
    else:
        # refresh name/username
        if user:
            if user.username:
                users[uid]["username"] = user.username
            if user.first_name:
                users[uid]["name"] = user.first_name
    return users[uid]



def log_payment(data, kind, uid, amount, status):
    data.setdefault("pay_log", []).append({
        "kind": kind, "uid": uid, "amount": float(amount or 0),
        "status": status, "time": time.time(),
    })

def take_bal(data, uid, amount) -> bool:
    uid = str(uid)
    u = data.get("users", {}).get(uid)
    if not u:
        return False
    bal = float(u.get("balance", 0) or 0)
    amount = float(amount)
    if bal < amount:
        return False
    u["balance"] = round(bal - amount, 2)
    return True


def add_bal(data, uid, amount):
    uid = str(uid)
    u = data.setdefault("users", {}).setdefault(uid, {
        "balance": 0.0, "ref_code": rid("R"), "referred_by": None,
        "referrals": 0, "wagered": 0.0, "won": 0.0, "lost": 0.0,
        "bets": 0, "username": "", "name": str(uid), "joined": str(date.today()),
    })
    u["balance"] = round(float(u.get("balance", 0) or 0) + float(amount), 2)


def apply_referral_first_deposit(data, uid, deposit_amt: float) -> float:
    """On referred user's 1st deposit: referrer gets ₹10 + 20% of deposit.
    Returns amount credited to referrer (0 if none)."""
    uid = str(uid)
    u = data.get("users", {}).get(uid) or {}
    if u.get("ref_deposit_paid"):
        return 0.0
    ref = u.get("referred_by")
    if not ref:
        return 0.0
    ou = data.get("users", {}).get(str(ref))
    if not ou:
        return 0.0
    flat = float(data.get("settings", {}).get("referral_bonus", REFERRAL_BONUS))
    pct = float(data.get("settings", {}).get("referral_deposit_pct", REFERRAL_DEPOSIT_PCT))
    commission = round(float(deposit_amt) * pct, 2)
    total = round(flat + commission, 2)
    ou["balance"] = round(float(ou.get("balance", 0) or 0) + total, 2)
    ou["ref_earnings"] = round(float(ou.get("ref_earnings", 0) or 0) + total, 2)
    u["ref_deposit_paid"] = True
    return total


def _mask_player_name(u: dict, uid: str) -> str:
    """Axom style: Name or Anonymous *****last4"""
    name = (u.get("name") or u.get("username") or "").strip()
    un = (u.get("username") or "").strip()
    last4 = str(uid)[-4:]
    if name and len(name) >= 2 and name != str(uid):
        # show short name + masked id style
        return f"{name[:12]}"
    if un:
        return f"{un[:12]}"
    return f"Anonymous *****{last4}"


def _game_emoji(game: str) -> str:
    g = (game or "").lower()
    mp = {
        "dice": "🎲", "dart": "🎯", "bowl": "🎳", "basket": "🏀", "football": "⚽",
        "coin": "🪙", "coin flip": "🪙", "limbo": "∞", "predict": "🔮",
        "dicejack": "🃏", "dj": "🃏", "7up7down": "🎲", "slot": "🎰", "slots": "🎰",
        "mines": "💣", "bj": "🃏", "blackjack": "🃏", "roulette": "🎡",
        "rps": "✂️", "battle": "⚔️", "crossy": "🐔", "chicken": "🐔",
    }
    for k, em in mp.items():
        if k in g:
            return em
    return "🎮"


def queue_win_feed(data, uid, game, stake, payout, net):
    """Queue Axom-style line for wins channel (only real wins)."""
    if net <= 0 or payout <= 0:
        return
    u = data.get("users", {}).get(str(uid)) or {}
    mult = round(payout / stake, 2) if stake > 0 else 0
    cur = (data.get("settings") or {}).get("display_currency") or "INR"
    sym = "₹" if cur in ("INR", "inr") else "$"
    data.setdefault("_pending_wins", []).append({
        "game": str(game),
        "emoji": _game_emoji(str(game)),
        "player": _mask_player_name(u, str(uid)),
        "amount": round(payout, 2),  # total won (payout)
        "profit": round(net, 2),
        "mult": mult,
        "sym": sym,
        "time": int(time.time()),
    })
    # keep queue short
    if len(data["_pending_wins"]) > 80:
        data["_pending_wins"] = data["_pending_wins"][-80:]


def record(data, uid, game, stake, win, payout):
    """Persist a settled bet and classify it by net payout (including pushes)."""
    del win
    uid = str(uid)
    u = data.get("users", {}).get(uid)
    if not u:
        return
    stake = float(stake)
    payout = max(0.0, float(payout or 0))
    net = round(payout - stake, 2)
    u["bets"] = int(u.get("bets", 0) or 0) + 1
    u["wagered"] = float(u.get("wagered", 0) or 0) + stake
    if net > 0:
        u["won"] = float(u.get("won", 0) or 0) + net
        u["wins"] = int(u.get("wins", 0) or 0) + 1
        u["streak"] = int(u.get("streak", 0) or 0) + 1
        queue_win_feed(data, uid, game, stake, payout, net)
    elif net < 0:
        u["lost"] = float(u.get("lost", 0) or 0) + abs(net)
        u["losses"] = int(u.get("losses", 0) or 0) + 1
        u["streak"] = 0
    else:
        u["draws"] = int(u.get("draws", 0) or 0) + 1
        u["streak"] = 0
    data.setdefault("bets", []).append({
        "uid": uid,
        "game": str(game),
        "stake": round(stake, 2),
        "win": net > 0,
        "result": "win" if net > 0 else "loss" if net < 0 else "push",
        "payout": round(payout, 2),
        "time": int(time.time()),
    })
    if len(data["bets"]) > 500:
        del data["bets"][:-500]
    stats = data.setdefault("stats", {})
    stats["bets"] = int(stats.get("bets", 0) or 0) + 1
    stats["wagered"] = round(float(stats.get("wagered", 0) or 0) + stake, 2)
    stats["paid"] = round(float(stats.get("paid", 0) or 0) + payout, 2)
    # jackpot 0.1%
    try:
        add = stake * 0.001
        data["jackpot_pool"] = float(data.get("jackpot_pool", 0) or 0) + add
    except Exception:
        pass


def parse_amount(args) -> float:
    if not args:
        return 0.0
    for a in args:
        s = str(a).replace(",", "").strip().lower()
        if s in ("all", "half", "max"):
            continue
        try:
            return float(s)
        except Exception:
            continue
    return 0.0


def parse_stake_rounds(data, uid, args):
    """Return (stake, rounds, use_all). Supports all / half and 2d2w style."""
    uid = str(uid)
    u = (data.get("users") or {}).get(uid) or {}
    bal = float(u.get("balance", 0) or 0)
    use_all = False
    stake = None
    rounds = 1
    for a in (args or []):
        s = str(a).lower().strip()
        if s == "all":
            use_all = True
            stake = bal
        elif s == "half":
            stake = round(bal / 2, 2)
        elif ("d" in s and s[0].isdigit() and len(s) <= 5):
            try:
                rounds = max(1, min(5, int(s[0])))
            except Exception:
                rounds = 1
        elif s.isdigit() and int(s) <= 3 and stake is not None:
            rounds = max(1, min(3, int(s)))
        else:
            try:
                v = float(s.replace(",", ""))
                if stake is None:
                    stake = v
                elif v <= 3:
                    rounds = int(v)
            except Exception:
                pass
    if use_all and bal > 0:
        stake = bal
    return stake, rounds, use_all



def need_wins_for(rounds) -> int:
    """Best-of: 1->1, 2->2, 3->2 wins needed (2d2w / 3d2w style)."""
    try:
        r = int(rounds or 1)
    except Exception:
        r = 1
    if r <= 1:
        return 1
    if r == 2:
        return 2
    return 2  # 3 rounds → first to 2


def parse_3dxw(s: str):
    """Parse 2d2w / 3d2w / 3d3w → rounds."""
    s = (s or "").lower().strip()
    if len(s) >= 3 and s[0].isdigit() and "d" in s:
        try:
            return max(1, min(5, int(s[0])))
        except Exception:
            pass
    return None


def get_lang(data, uid) -> str:
    u = (data.get("users") or {}).get(str(uid)) or {}
    return u.get("lang") or data.get("settings", {}).get("lang") or "en"


def t(data, uid, key, **kw) -> str:
    """Simple i18n — English default."""
    lang = get_lang(data, uid)
    EN = {
        "need_group": "Games only work in the main group. Join the group first.",
        "dep_group": "Deposit only in private DM with the bot.",
        "wd_group": "Withdraw only in private DM. Min ₹{min_wd}",
        "dep_ask": "How much do you want to deposit? (Min ₹{min_dep})",
        "wd_ask_upi": "Send your UPI ID first.",
        "low_bal": "Low balance: ₹{bal:.0f} (need ₹{need:.0f})",
        "lang_set": "Language set.",
        "lang_usage": "Language\n/language en",
        "help_title": "HR CASINO · Premium Game Arena",
        "help_games": "GAMES",
        "help_wallet": "WALLET",
        "help_extra": "EXTRA",
        "help_admin": "ADMIN",
        "help_note": "Games → group only · Pay → DM only",
        "wallet": "WALLET\n{name}\nBalance: ₹{bal:.0f}",
        "stake_range": "Stake ₹{mn:.0f} – ₹{mx:.0f}",
    }
    HI = EN  # full English
    table = HI if lang in ("hi", "hinglish") else EN
    s = table.get(key) or EN.get(key) or key
    try:
        return s.format(**kw)
    except Exception:
        return s


def find_target(update, args):
    """Resolve target user id from reply, text mention entities, or numeric id."""
    msg = update.effective_message or (update.message if update else None)
    if msg and msg.reply_to_message and msg.reply_to_message.from_user:
        return msg.reply_to_message.from_user.id
    # text_mention / mention entities
    if msg and msg.entities and msg.text:
        for ent in msg.entities:
            if ent.type == "text_mention" and ent.user:
                return ent.user.id
            if ent.type == "mention":
                uname = msg.text[ent.offset+1:ent.offset+ent.length].lower()
                try:
                    data = load()
                    for uid, u in (data.get("users") or {}).items():
                        if (u.get("username") or "").lower() == uname:
                            return int(uid)
                except Exception:
                    pass
    if not args:
        return None
    for a in args:
        s = str(a).strip()
        if s.startswith("@"):
            uname = s[1:].lower()
            # search known users by username
            try:
                data = load()
                for uid, u in (data.get("users") or {}).items():
                    if (u.get("username") or "").lower() == uname:
                        return int(uid)
            except Exception:
                pass
            continue
        if s.isdigit():
            return int(s)
    return None


def has_nova_tag(user) -> bool:
    name = (user.full_name or "") + " " + (user.username or "")
    return "novaversebet" in name.lower().replace(" ", "")


def display_user(u, uid) -> str:
    if u.get("username"):
        return "@" + u["username"]
    return u.get("name") or str(uid)


def is_group(update) -> bool:
    chat = update.effective_chat
    return chat and chat.type in ("group", "supergroup")


def is_target_group(update) -> bool:
    """True if chat is main GROUP_ID or any /allow-listed group."""
    chat = update.effective_chat
    if not chat:
        return False
    try:
        data = load()
        gid = int(data.get("settings", {}).get("group_id") or GROUP_ID)
        if chat.id == gid:
            return True
        allowed = data.get("allowed_groups") or []
        return int(chat.id) in [int(x) for x in allowed]
    except Exception:
        return chat.id == GROUP_ID


async def require_group(update, context) -> bool:
    """Games in allowed groups only. Owner: /allow in group to enable."""
    if is_target_group(update):
        return True
    data = load()
    uid = update.effective_user.id if update.effective_user else 0
    link = data.get("settings", {}).get("group_link") or GROUP_LINK
    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("Join Group", url=link)
    ]])
    msg = t(data, uid, "need_group")
    if update.callback_query:
        try:
            await update.callback_query.answer(msg[:180], show_alert=True)
        except Exception:
            pass
        try:
            await update.callback_query.message.reply_text(msg, reply_markup=kb)
        except Exception:
            pass
    elif update.message:
        try:
            await update.message.reply_text(msg, reply_markup=kb)
        except Exception:
            pass
    return False




def _pil_font(size=24, bold=False):
    from PIL import ImageFont
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "arial.ttf",
    ]
    for c in candidates:
        try:
            return ImageFont.truetype(c, size)
        except Exception:
            continue
    return ImageFont.load_default()


def _circle_crop(im, size):
    from PIL import Image, ImageDraw
    im = im.convert("RGBA").resize((size, size), Image.LANCZOS)
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, size, size), fill=255)
    out = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    out.paste(im, (0, 0), mask)
    return out


def make_welcome_banner() -> str:
    from PIL import Image, ImageDraw
    W, H = 1200, 675
    img = Image.new("RGB", (W, H), (8, 4, 28))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([30, 30, W-30, H-30], radius=40, outline=(160, 80, 255), width=4)
    d.text((W//2 - 220, 180), "HR CASINO", fill=(220, 180, 255), font=_pil_font(64, True))
    d.text((W//2 - 160, 280), "PLAYERS BOT", fill=(180, 140, 255), font=_pil_font(36, True))
    d.text((W//2 - 200, 400), "FAST  ·  SECURE  ·  TRUSTED", fill=(150, 150, 180), font=_pil_font(24, True))
    out = "nova_welcome_gen.png"
    img.save(out, "PNG")
    return out


def make_stats_card(user, u, data, avatar_path=None) -> str:
    """BlockVerse-style official player report — large fonts, purple cards."""
    from PIL import Image, ImageDraw
    W, H = 900, 1100
    bg = (232, 228, 245)
    purple = (55, 30, 95)
    card = (72, 42, 130)
    card2 = (85, 50, 150)
    white = (255, 255, 255)
    muted = (180, 165, 210)
    green = (80, 220, 160)
    green_bg = (200, 245, 220)
    pink = (255, 140, 180)
    gold = (255, 210, 80)

    img = Image.new("RGB", (W, H), bg)
    d = ImageDraw.Draw(img)

    # main dark panel
    d.rounded_rectangle([30, 30, W-30, H-30], radius=40, fill=purple)

    # top white header strip
    d.rounded_rectangle([50, 50, W-50, 150], radius=22, fill=white)
    # lock icon circle
    d.ellipse([70, 72, 120, 122], fill=(50, 30, 100))
    d.text((82, 84), "B", fill=white, font=_pil_font(28, True))
    d.text((140, 68), "HR CASINO", fill=(30, 20, 60), font=_pil_font(22, True))
    d.text((140, 98), "PLAY. WIN. REPEAT.", fill=(120, 110, 150), font=_pil_font(12, True))
    d.text((W//2 - 40, 62), "OFFICIAL PLAYER REPORT", fill=(100, 90, 130), font=_pil_font(12, True))
    d.text((W//2 - 80, 88), "ALL-TIME STATEMENT", fill=(20, 15, 40), font=_pil_font(22, True))
    # UP badge
    d.rounded_rectangle([W-180, 75, W-70, 120], radius=18, fill=green_bg)
    d.ellipse([W-168, 88, W-150, 106], fill=green)
    d.text((W-142, 88), "UP", fill=(20, 100, 70), font=_pil_font(16, True))

    # avatar
    ax, ay, asz = 70, 180, 120
    if avatar_path:
        try:
            from PIL import Image as _I
            av = _circle_crop(_I.open(avatar_path), asz)
            img.paste(av, (ax, ay), av)
        except Exception:
            d.ellipse([ax, ay, ax+asz, ay+asz], fill=(100, 60, 180))
    else:
        d.ellipse([ax, ay, ax+asz, ay+asz], fill=(100, 60, 180))
        ini = (user.first_name or "N")[:1].upper()
        d.text((ax+40, ay+35), ini, fill=white, font=_pil_font(42, True))

    name = (user.first_name or "Player")[:16]
    un = f"@{user.username}" if user.username else f"ID {user.id}"
    # name blocks style
    d.text((220, 190), name, fill=white, font=_pil_font(28, True))
    d.text((220, 230), un, fill=muted, font=_pil_font(18, True))
    # id pill
    d.rounded_rectangle([220, 265, 420, 300], radius=12, fill=(40, 25, 80))
    d.text((235, 272), f"ID {user.id}", fill=muted, font=_pil_font(14, True))
    d.rounded_rectangle([435, 265, 540, 300], radius=12, fill=(90, 55, 150))
    d.text((450, 272), "Player", fill=white, font=_pil_font(14, True))

    bal = float(u.get("balance", 0) or 0)
    wag = float(u.get("wagered", 0) or 0)
    won = float(u.get("won", 0) or 0)
    lost = float(u.get("lost", 0) or 0)
    bets = int(u.get("bets", 0) or 0)
    wins_n = int(u.get("wins", 0) or 0)
    losses_n = int(u.get("losses", 0) or 0)
    if wins_n == 0 and losses_n == 0 and bets:
        # estimate from won/lost presence
        wins_n = max(0, bets // 2)
        losses_n = max(0, bets - wins_n)
    settled = max(wins_n + losses_n, bets, 1)
    wr = (wins_n / settled * 100) if settled else 0.0
    net = won - lost
    ranked = sorted(data.get("users", {}).items(), key=lambda kv: float(kv[1].get("wagered", 0)), reverse=True)
    rank = next((i for i, (uid, _) in enumerate(ranked, 1) if uid == str(user.id)), 0)
    joined = str(u.get("joined", "—"))[:10]

    # global rank + member since
    d.text((620, 185), "GLOBAL RANK", fill=muted, font=_pil_font(12, True))
    d.text((620, 210), f"#{rank}" if rank else "#—", fill=white, font=_pil_font(28, True))
    d.text((760, 185), "MEMBER SINCE", fill=muted, font=_pil_font(12, True))
    d.text((760, 210), joined, fill=white, font=_pil_font(16, True))

    # win streak badge
    streak = int(u.get("streak", 0) or 0)
    d.rounded_rectangle([620, 265, 860, 305], radius=16, fill=(40, 120, 90))
    d.ellipse([635, 277, 655, 297], fill=green)
    d.text((665, 275), f"{max(streak, 0)} WIN STREAK", fill=white, font=_pil_font(14, True))

    # WIN RATE card
    d.rounded_rectangle([55, 340, 430, 560], radius=24, fill=card)
    d.text((80, 360), "WIN RATE", fill=muted, font=_pil_font(14, True))
    d.text((80, 395), f"{wr:.1f}%", fill=white, font=_pil_font(52, True))
    d.text((80, 470), f"{settled} settled games", fill=muted, font=_pil_font(14, True))
    d.rounded_rectangle([80, 510, 220, 545], radius=14, fill=green_bg)
    d.text((95, 518), f"{wins_n} WINS", fill=(20, 100, 70), font=_pil_font(14, True))
    d.rounded_rectangle([235, 510, 390, 545], radius=14, fill=(255, 200, 210))
    d.text((250, 518), f"{losses_n} LOSSES", fill=(160, 40, 70), font=_pil_font(14, True))

    # NET P/L card
    d.rounded_rectangle([450, 340, 845, 560], radius=24, fill=card)
    d.text((475, 360), "NET P/L  /  ALL TIME", fill=muted, font=_pil_font(14, True))
    net_col = green if net >= 0 else pink
    sign = "+" if net >= 0 else ""
    d.text((475, 400), f"{sign}Rs {net:.0f}", fill=net_col, font=_pil_font(42, True))
    # mini sparkline
    pts = []
    base_y = 520
    for i in range(12):
        x = 480 + i * 28
        y = base_y - (15 + (i * 7) % 40)
        pts.append((x, y))
    if len(pts) > 1:
        d.line(pts, fill=green, width=3)
        d.ellipse([pts[-1][0]-5, pts[-1][1]-5, pts[-1][0]+5, pts[-1][1]+5], fill=white)
    d.rounded_rectangle([475, 510, 620, 545], radius=14, fill=green_bg)
    d.ellipse([488, 522, 504, 538], fill=green)
    d.text((512, 518), "PROFITABLE" if net >= 0 else "IN LOSS", fill=(20, 100, 70), font=_pil_font(13, True))

    # bottom 6 tiles
    tiles = [
        ("TOTAL GAMES", str(settled), white),
        ("TOTAL WAGER", f"Rs {wag/1000:.1f}K" if wag >= 1000 else f"Rs {wag:.0f}", gold),
        ("FAVOURITE GAME", "Dice", (200, 160, 255)),
        ("TOTAL DEPOSIT", f"Rs {float(u.get('deposited', 0) or 0):.0f}", green),
        ("TOTAL WITHDRAWAL", f"Rs {float(u.get('withdrawn', 0) or 0):.0f}", gold),
        ("TOTAL P/L", f"{sign}Rs {net:.0f}", green if net >= 0 else pink),
    ]
    positions = [
        (55, 580), (320, 580), (585, 580),
        (55, 740), (320, 740), (585, 740),
    ]
    tw, th = 250, 140
    for (label, val, col), (x, y) in zip(tiles, positions):
        d.rounded_rectangle([x, y, x+tw, y+th], radius=20, fill=card2)
        d.ellipse([x+16, y+18, x+28, y+30], fill=col)
        d.text((x+36, y+16), label, fill=muted, font=_pil_font(12, True))
        d.text((x+20, y+55), val, fill=col, font=_pil_font(28, True))

    # footer bar
    d.rounded_rectangle([55, 920, W-55, 1000], radius=18, fill=(245, 240, 255))
    d.ellipse([75, 950, 95, 970], fill=(120, 80, 200))
    d.text((110, 948), "HR CASINO PLAYER STATEMENT", fill=(50, 30, 90), font=_pil_font(14, True))
    d.text((520, 948), "PLAY RESPONSIBLY  /  HR CASINO", fill=(140, 120, 180), font=_pil_font(12, True))

    out = f"stats_{user.id}.png"
    img.save(out, "PNG")
    return out


def make_leaderboard_card(data, viewer_id=None, avatar_map=None) -> str:
    from PIL import Image, ImageDraw
    W, H = 900, 1200
    img = Image.new("RGB", (W, H), (10, 6, 28))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([20, 20, W-20, H-20], radius=32, outline=(140, 90, 255), width=3)
    d.rounded_rectangle([40, 40, W-40, 160], radius=22, fill=(255, 255, 255))
    d.text((70, 70), "HR CASINO", fill=(20, 12, 40), font=_pil_font(34, True))
    d.text((70, 115), "WAGER LEADERBOARD", fill=(100, 90, 130), font=_pil_font(16, True))
    items = sorted(data.get("users", {}).items(), key=lambda kv: float(kv[1].get("wagered", 0)), reverse=True)[:10]
    y = 200
    colors = [(255, 200, 50), (200, 210, 230), (220, 150, 80)]
    for i, (uid, u) in enumerate(items, 1):
        bg = (28, 20, 55) if i > 3 else (36, 28, 70)
        d.rounded_rectangle([50, y, W-50, y+80], radius=16, fill=bg)
        col = colors[i-1] if i <= 3 else (120, 100, 180)
        d.ellipse([70, y+15, 130, y+75], fill=col)
        d.text((88, y+28), str(i), fill=(20, 10, 30), font=_pil_font(22, True))
        nx = 160
        if avatar_map and uid in avatar_map:
            try:
                from PIL import Image as _I
                av = _circle_crop(_I.open(avatar_map[uid]), 50)
                img.paste(av, (150, y+15), av)
                nx = 220
            except Exception:
                pass
        nm = (u.get("username") and ("@" + u["username"]) or u.get("name") or uid)[:18]
        d.text((nx, y+18), nm, fill=(255, 255, 255), font=_pil_font(22, True))
        d.text((nx, y+48), f"Wagered Rs {float(u.get('wagered',0)):.0f}", fill=(160, 150, 200), font=_pil_font(16, True))
        if viewer_id and str(viewer_id) == str(uid):
            d.text((W-200, y+28), "YOU", fill=(100, 255, 180), font=_pil_font(18, True))
        y += 95
    if not items:
        d.text((120, 400), "No rankings yet — start playing!", fill=(180, 170, 210), font=_pil_font(22, True))
    out = "leaderboard.png"
    img.save(out, "PNG")
    return out


def make_bj_card(player, dealer, pv, dv, stake, status, footer, hide_dealer=False) -> str:
    """Blackjack table card — large ranks, green felt look."""
    from PIL import Image, ImageDraw
    W, H = 900, 1000
    img = Image.new("RGB", (W, H), (12, 55, 32))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([20, 20, W-20, H-20], radius=32, outline=(80, 200, 120), width=4)
    d.text((40, 40), "BLACKJACK", fill=(180, 255, 200), font=_pil_font(36, True))
    d.text((40, 95), f"Bet  Rs {stake:.0f}", fill=(200, 230, 200), font=_pil_font(22, True))

    def draw_hand(cards, y, title, score, hide=False):
        d.text((40, y), title, fill=(150, 210, 170), font=_pil_font(18, True))
        x = 40
        show = ["??"] if hide else [str(c) for c in cards]
        for c in show:
            # card rectangle
            d.rounded_rectangle([x, y+40, x+110, y+190], radius=12, fill=(250, 250, 255), outline=(30, 30, 40), width=2)
            col = (200, 40, 40) if any(s in str(c) for s in ("♥", "♦", "H", "D")) else (20, 20, 30)
            if hide:
                d.rectangle([x+8, y+48, x+102, y+182], fill=(30, 60, 120))
                d.text((x+30, y+100), "?", fill=(200, 220, 255), font=_pil_font(40, True))
            else:
                d.text((x+18, y+55), str(c)[:4], fill=col, font=_pil_font(28, True))
            x += 125
        if not hide:
            d.text((40, y+210), f"Score  {score}", fill=(255, 230, 100), font=_pil_font(26, True))

    draw_hand(dealer, 150, "DEALER", dv, hide=hide_dealer)
    draw_hand(player, 420, "PLAYER", pv, hide=False)

    d.rounded_rectangle([40, 720, W-40, 820], radius=18, fill=(20, 70, 45))
    d.text((60, 755), str(status)[:42], fill=(255, 255, 255), font=_pil_font(26, True))
    d.text((40, 860), str(footer)[:55], fill=(180, 220, 190), font=_pil_font(20, True))
    out = "bj_card.png"
    img.save(out, "PNG")
    return out


def make_limbo_card(stake, target, roll, win, payout, bal) -> str:
    from PIL import Image, ImageDraw
    W, H = 800, 700
    img = Image.new("RGB", (W, H), (16, 8, 36))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([20, 20, W-20, H-20], radius=28, outline=(160, 80, 255), width=3)
    d.text((50, 50), "LIMBO", fill=(220, 180, 255), font=_pil_font(36, True))
    d.text((50, 120), f"Target x{target}", fill=(180, 160, 220), font=_pil_font(22, True))
    d.text((50, 180), f"Roll  {roll:.2f}x", fill=(255, 255, 255), font=_pil_font(48, True))
    col = (80, 255, 140) if win else (255, 90, 120)
    d.text((50, 280), "WIN" if win else "LOSE", fill=col, font=_pil_font(40, True))
    d.text((50, 360), (f"+Rs {payout - stake:.0f}" if win else f"-Rs {stake:.0f}"), fill=col, font=_pil_font(28, True))
    d.text((50, 480), f"Balance Rs {bal:.0f}", fill=(180, 170, 210), font=_pil_font(20, True))
    out = "limbo_card.png"
    img.save(out, "PNG")
    return out


def private_menu_markup(data):
    """Safe menu — no tg:// URLs (they break whole keyboard on some clients)."""
    B = InlineKeyboardButton
    rows = []
    group_link = data.get("settings", {}).get("group_link") or GROUP_LINK
    if group_link and "YOUR_INVITE_HASH" not in str(group_link):
        rows.append([B("🎮 Join game group", url=group_link)])
    rows.extend([
        [B("💰 Wallet", callback_data="menu_wallet"), B("👤 Profile", callback_data="menu_stats")],
        [B("💰 Deposit", callback_data="menu_deposit"), B("🚀 Withdraw", callback_data="menu_withdraw")],
        [B("🎲 Games", callback_data="menu_games"), B("🧾 History", callback_data="menu_history")],
        [B("🎉 Jackpot", callback_data="menu_jackpot"), B("📖 Help", callback_data="menu_help")],
        [B("📜 Terms", callback_data="menu_rules")],
    ])
    return InlineKeyboardMarkup(rows)


async def _menu_edit(q, text: str, reply_markup=None):
    """Edit callback message; if edit fails, reply new message (buttons always work)."""
    try:
        await q.edit_message_text(text, parse_mode="HTML", reply_markup=reply_markup)
        return
    except Exception as e:
        logger.warning("menu edit failed: %s", e)
    try:
        await q.message.reply_text(text, parse_mode="HTML", reply_markup=reply_markup)
    except Exception as e2:
        logger.warning("menu reply failed: %s", e2)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Rolex Casino style /start — full welcome card + menu (DM & group)."""
    try:
        data = load()
        user = update.effective_user
        msg = update.effective_message
        if not user or not msg:
            return
        if is_banned(data, user.id):
            await msg.reply_text("🚫 You are banned.")
            return
        u = ensure_user(data, user)
        if context.args:
            arg0 = context.args[0].strip()
            if arg0.lower() == "withdraw":
                if is_group(update):
                    me = await context.bot.get_me()
                    kb = InlineKeyboardMarkup([[InlineKeyboardButton("💳 Withdraw in DM", url=f"https://t.me/{me.username}?start=withdraw")]])
                    await msg.reply_text(
                        f"⬆️ <b>Withdraw</b>\n<blockquote>Open DM to request payout.\nMin: ₹{MIN_WITHDRAW}</blockquote>",
                        parse_mode="HTML",
                        reply_markup=kb,
                    )
                    return
                context.args = []
                await cmd_withdraw(update, context)
                return
            if arg0.lower() == "deposit":
                if is_group(update):
                    me = await context.bot.get_me()
                    kb = InlineKeyboardMarkup([[InlineKeyboardButton("💰 Deposit in DM", url=f"https://t.me/{me.username}?start=deposit")]])
                    await msg.reply_text(
                        "⬇️ <b>Deposit</b>\n<blockquote>Open DM to top up your wallet.</blockquote>",
                        parse_mode="HTML",
                        reply_markup=kb,
                    )
                    return
                context.args = []
                await cmd_deposit(update, context)
                return
            ref = arg0.upper()
            if not u.get("referred_by") and ref != u.get("ref_code"):
                for oid, ou in data["users"].items():
                    if ou.get("ref_code") == ref and oid != str(user.id):
                        # Link only — bonus on FIRST deposit (₹10 + 20%)
                        u["referred_by"] = oid
                        u["ref_deposit_paid"] = False
                        ou["referrals"] = int(ou.get("referrals", 0) or 0) + 1
                        save(data)
                        try:
                            await msg.reply_text(
                                "🎁 Referral linked!\n"
                                "Sponsor earns <b>₹10 + 20%</b> when you complete your <b>1st deposit</b>.",
                                parse_mode="HTML",
                            )
                        except Exception:
                            pass
                        break
        bal = float(u.get("balance", 0) or 0)
        me = await context.bot.get_me()
        name = user.first_name or "Player"
        uname = ("@" + user.username) if user.username else name
        gname = (data.get("settings") or {}).get("group_name", GROUP_NAME) or "HR CASINO"
        try:
            money = fmt_money(data, user.id, bal)
        except Exception:
            money = f"₹{bal:.2f}"
        vip = int(u.get("vip_level", 0) or 0)
        vip_label = ["Bronze", "Silver", "Gold", "Platinum", "Diamond"][min(max(vip, 0), 4)]
        wagered = float(u.get("wagered", 0) or 0)

        uname_bot = getattr(me, "username", None)
        try:
            kb = rolex_main_kb(uname_bot)
        except Exception as e_kb:
            logger.warning("rolex_main_kb failed: %s", e_kb)
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("💰 Wallet", callback_data="menu_wallet"),
                 InlineKeyboardButton("😊 Profile", callback_data="menu_stats")],
                [InlineKeyboardButton("🎲 Games", callback_data="menu_games"),
                 InlineKeyboardButton("🧾 History", callback_data="menu_history")],
                [InlineKeyboardButton("💰 Deposit", callback_data="menu_deposit"),
                 InlineKeyboardButton("🚀 Withdraw", callback_data="menu_withdraw")],
                [InlineKeyboardButton("📖 Help", callback_data="menu_help")],
            ])
        group_link = (data.get("settings") or {}).get("group_link") or GROUP_LINK
        if not is_group(update) and group_link and "YOUR_INVITE_HASH" not in str(group_link):
            try:
                rows = list(kb.inline_keyboard)
                rows.insert(0, [InlineKeyboardButton("🎮 Join Game Group", url=group_link)])
                kb = InlineKeyboardMarkup(rows)
            except Exception:
                pass

        text = (
            f"⭐ <b>{gname}</b>\n"
            f"<blockquote>"
            f"<b>WELCOME</b>\n"
            f"👤 <b>{name}</b> · {uname}\n"
            f"💰 Balance: <b>{money}</b>\n"
            f"🏆 VIP: {vip_label}\n"
            f"📊 Wagered: ₹{wagered:.0f}\n"
            f"</blockquote>\n"
            f"🎲 Games in group · 💳 Wallet in DM\n"
            f"👇 Use the menu below"
        )
        simple_kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("💰 Wallet", callback_data="menu_wallet"),
             InlineKeyboardButton("👤 Profile", callback_data="menu_stats")],
            [InlineKeyboardButton("🎲 Games", callback_data="menu_games"),
             InlineKeyboardButton("🧾 History", callback_data="menu_history")],
            [InlineKeyboardButton("💰 Deposit", callback_data="menu_deposit"),
             InlineKeyboardButton("🚀 Withdraw", callback_data="menu_withdraw")],
            [InlineKeyboardButton("📖 Help", callback_data="menu_help"),
             InlineKeyboardButton("🎉 Jackpot", callback_data="menu_jackpot")],
        ])
        try:
            await msg.reply_text(text, parse_mode="HTML", reply_markup=kb)
        except Exception as e_send:
            logger.warning("start full kb failed: %s — simple kb", e_send)
            try:
                await msg.reply_text(text, parse_mode="HTML", reply_markup=simple_kb)
            except Exception as e2:
                logger.warning("start simple kb failed: %s", e2)
                await msg.reply_text(text, parse_mode="HTML")
                await msg.reply_text("Menu:", reply_markup=simple_kb)
    except Exception as e:
        logger.exception("start failed: %s", e)
        try:
            m = update.effective_message
            if m:
                kb = InlineKeyboardMarkup([
                    [InlineKeyboardButton("💰 Wallet", callback_data="menu_wallet"),
                     InlineKeyboardButton("💰 Deposit", callback_data="menu_deposit")],
                    [InlineKeyboardButton("📖 Help", callback_data="menu_help")],
                ])
                await m.reply_text(
                    "⭐ <b>HR CASINO</b>\n<blockquote>Welcome!\nUse menu or /help · /wallet · /deposit</blockquote>",
                    parse_mode="HTML",
                    reply_markup=kb,
                )
        except Exception:
            pass


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load()
    ensure_user(data, update.effective_user)
    nl = chr(10)
    parts = [
        ("spark",), " HRCasinoBOT — Game Arena ", ("spark",), nl, nl,
        ("alert",), " Challenge anyone to a 1v1 battle!", nl, nl,
        ("heart",), " Commands", nl,
        "┣ /battle @user — start a battle", nl,
        "┣ /battle @user 3 — multi-round (1–3)", nl,
        "┣ /coin 50 heads — coin flip", nl,
        "┣ /rps 50 — Rock Paper Scissors", nl,
        "┣ /jackpot — jackpot pool", nl,
        "┣ /dice @user 50 — PvP dice", nl,
        "┣ /basket @user 50 — PvP basketball", nl,
        "┣ /dice 50 — vs bot", nl,
        "┣ /dr high 50 — Dice Roulette", nl,
        "┣ /predict 50 1 3 5 — pick numbers (max 5)", nl,
        "┣ /dj 50 high — Dice Jack (2 dice)", nl,
        "┣ /7up 50 up — 7 Up / 7 Down", nl,
        "┣ /basket 50 · /dart 50 · /bowl 50", nl,
        "┣ /slot 50 · /mines 50 · /bj 20", nl,
        "┣ /limbo 50 2 — limbo", nl,
        "┣ /invite · /tip @user 10", nl,
        "┣ /bonus · /wagerstatus · /mystats", nl,
        "┣ /cancel · /allow · /topwager · /leaderboard", nl,
        "┣ /wallet · /deposit · /withdraw", nl,
        "┣ /promo CODE · /payments", nl,
        "┗ /help", nl, nl,
        ("game",), " Games: Dice Darts Basket Football Bowl Slots RPS Mines Coin BJ Limbo 7Up", nl, nl,
        ("bank",), " Betting in group · Pay in DM",
    ]
    if is_owner(data, update.effective_user.id):
        parts.extend([nl, nl, ("crown",), " Owner tools: /panel · /admincommands"])
    await reply_prem(update.message, parts)


async def cmd_commands(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await cmd_help(update, context)


async def cmd_wallet(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """BlockVerse / Nova style balance card."""
    try:
        data = load()
        user = update.effective_user
        u = ensure_user(data, user)
        save(data)
        bal = float(u.get("balance", 0) or 0)
        wagered = float(u.get("wagered", 0) or 0)
        won = float(u.get("won", 0) or 0)
        me = await context.bot.get_me()
        B = InlineKeyboardButton
        kb = InlineKeyboardMarkup([
            [
                B("⬇️ Deposit", url=f"https://t.me/{me.username}?start=deposit"),
                B("⬆️ Withdraw", url=f"https://t.me/{me.username}?start=withdraw"),
            ],
            [B("📊 Stats", callback_data="menu_stats"), B("🎮 Games", callback_data="menu_games")],
        ])
        name = user.first_name or "Player"
        un = f"@{user.username}" if user.username else name
        nl = chr(10)
        parts = [
            ("bank",), " Wallet", nl, nl,
            ("user",), f" {un}", nl,
            ("money",), f" Balance: ₹{bal:,.2f}", nl,
            ("chart",), f" Wagered: ₹{wagered:,.2f}", nl,
            ("trophy",), f" Won: ₹{won:,.2f}", nl,
        ]
        try:
            await reply_prem(update.message, parts, reply_markup=kb)
        except Exception:
            await update.message.reply_text(
                f"🏦 <b>Wallet</b>\n\n"
                f"👤 {un}\n"
                f"💰 Balance: <b>₹{bal:,.2f}</b>\n"
                f"📊 Wagered: ₹{wagered:,.2f}\n"
                f"🏆 Won: ₹{won:,.2f}",
                parse_mode="HTML",
                reply_markup=kb,
            )
    except Exception as e:
        logger.exception("wallet")
        await update.message.reply_text("Error: " + str(e))


async def cmd_deposit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load()
    user = update.effective_user
    ensure_user(data, user)
    msg = update.effective_message
    if is_group(update):
        me = await context.bot.get_me()
        kb = InlineKeyboardMarkup([[
            style_btn("💰 Deposit in DM", style="success", url=f"https://t.me/{me.username}?start=deposit")
        ]])
        await msg.reply_text(
            "⬇️ <b>Deposit</b>\n<blockquote>Open DM to choose UPI / Crypto.</blockquote>",
            parse_mode="HTML",
            reply_markup=kb,
        )
        return
    # Deposit grid — no Binance
    B = InlineKeyboardButton
    rows = [
        [B("🇮🇳 UPI (India)", callback_data="dep_method_upi"),
         B("🤖 @cctip_bot", callback_data="dep_method_cctip")],
        [B("💛 CWallet", callback_data="dep_method_cwallet")],
        [B("₿ BTC", callback_data="dep_crypto_BTC"),
         B("◎ SOL", callback_data="dep_crypto_SOL")],
        [B("Ξ ETH", callback_data="dep_crypto_ETH"),
         B("💎 TON", callback_data="dep_crypto_TON")],
        [B("₮ USDT TRC20", callback_data="dep_crypto_USDT_TRC20"),
         B("₮ USDT BEP20", callback_data="dep_crypto_USDT_BEP20")],
        [B("₮ USDT ERC20", callback_data="dep_crypto_USDT_ERC20"),
         B("⬡ BNB", callback_data="dep_crypto_BNB")],
        [B("🟣 Polygon", callback_data="dep_crypto_POLYGON"),
         B("🔵 Arbitrum", callback_data="dep_crypto_ARBITRUM")],
        [B("📋 All addresses", callback_data="dep_crypto_more")],
    ]
    gw = (data.get("settings") or {}).get("gateway_upi") or {}
    gw_line = "· UPI Gateway: ON\n" if gw.get("key") else "· UPI · unique amount match\n"
    await msg.reply_text(
        f"💰 <b>HR CASINO · Deposit</b>\n\n"
        f"Min: ₹{min_dep_val(data):.0f}\n"
        f"Pick a method:\n\n"
        f"{gw_line}"
        f"· CWallet / @cctip_bot · tip then proof\n"
        f"· Crypto · address + screenshot",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(rows),
    )


async def start_upi_deposit(update, context, user):
    data = load()
    upi = (data.get("settings") or {}).get("upi") or UPI_ID
    if not upi:
        await update.effective_message.reply_text(
            "⚠️ UPI not set yet.\nOwner: reply any message with UPI + QR then send /setupiandqr\n"
            "Or /setupi YOUR_UPI@paytm"
        )
        return
    data.setdefault("pending_dep_step", {})[str(user.id)] = {"step": "amount", "method": "upi"}
    save(data)
    await update.effective_message.reply_text(
        f"🇮🇳 <b>UPI Deposit</b>\n"
        f"<blockquote>"
        f"Min: ₹{min_dep_val(data):.0f}\n"
        f"Send amount as number (example: <code>500</code>)\n\n"
        f"Bot will give a <b>unique amount</b> like ₹500.37\n"
        f"Pay exact → owner auto-matches with /creditbyamount\n"
        f"</blockquote>",
        parse_mode="HTML",
    )


async def start_cc_deposit(update, context, user):
    """Deposit via Telegram bot @cctip_bot — user tips/sends, then proof here."""
    data = load()
    uid = str(user.id)
    ensure_user(data, user)
    data.setdefault("pending_dep_step", {})[uid] = {
        "step": "amount",
        "method": "cctip",
        "time": time.time(),
    }
    save(data)
    log_deposit(uid, "cctip_start", 0, "waiting_amount")
    mn = min_dep_val(data)
    await update.effective_message.reply_text(
        f"🤖 <b>HR CASINO · @cctip_bot Deposit</b>\n"
        f"<blockquote>"
        f"Min: ₹{mn:.0f}\n\n"
        f"1. Send the <b>amount</b> here (number only)\n"
        f"2. Open <b>@cctip_bot</b> and send/tip that amount to our wallet\n"
        f"3. Come back and send <b>screenshot / proof</b>\n"
        f"4. Admin credits balance after verify\n"
        f"</blockquote>\n"
        f"Send amount now (example: <code>500</code>)",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🤖 Open @cctip_bot", url="https://t.me/cctip_bot")],
            [InlineKeyboardButton(f"💬 Support @{SUPPORT_PAY}", url=f"https://t.me/{SUPPORT_PAY}")],
            [InlineKeyboardButton("⬅️ Back", callback_data="dep_method_back")],
        ]),
    )


async def start_binance_deposit(update, context, user):
    data = load()
    uid = str(user.id)
    # unique memo so auto-credit can match
    memo = f"HR{uid[-8:]}{secrets.token_hex(2).upper()}"
    data.setdefault("pending_binance", {})[uid] = {
        "memo": memo,
        "time": time.time(),
        "status": "waiting",
    }
    save(data)
    addr_info = await binance_deposit_address()
    addr = ""
    tag = ""
    if isinstance(addr_info, dict) and not addr_info.get("error"):
        addr = addr_info.get("address") or ""
        tag = addr_info.get("tag") or addr_info.get("memo") or ""
    if not addr:
        addr = data.get("settings", {}).get("binance_address") or "(set BINANCE_API_SECRET + enable deposit read, or /setbinanceaddr)"
    body = (
        f"<b>🟡 Binance Deposit (USDT)</b>\n\n"
        f"<blockquote>"
        f"Network: <b>{BINANCE_DEPOSIT_NETWORK}</b> (TRC20 recommended)\n"
        f"Coin: <b>{BINANCE_DEPOSIT_COIN}</b>\n"
        f"Address:\n<code>{addr}</code>\n"
    )
    if tag:
        body += f"Memo/Tag: <code>{tag}</code>\n"
    body += (
        f"Your ID memo: <code>{memo}</code>\n"
        f"</blockquote>\n"
        f"1) Send USDT to address\n"
        f"2) Put memo in note if asked\n"
        f"3) Tap <b>I Paid</b> — bot checks Binance\n"
        f"<i>Auto-credit needs API secret + deposit history permission.</i>"
    )
    kb = InlineKeyboardMarkup([
        [style_btn("✅ I Paid — Check", style="success", callback_data="binance_check")],
        [style_btn("🔙 Back", style="primary", callback_data="dep_method_back")],
    ])
    msg = update.callback_query.message if update.callback_query else update.message
    await msg.reply_text(body, parse_mode="HTML", reply_markup=kb)


async def cmd_withdraw(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load()
    user = update.effective_user
    u = ensure_user(data, user)
    if is_group(update):
        me = await context.bot.get_me()
        kb = InlineKeyboardMarkup([[
            style_btn("⬆️ Withdraw", style="success", url=f"https://t.me/{me.username}?start=withdraw")
        ]])
        await update.message.reply_text(
            t(data, user.id, "wd_group", min_wd=MIN_WITHDRAW),
            parse_mode="Markdown",
            reply_markup=kb,
        )
        return
    bal = float(u.get("balance", 0))
    min_wd = float(data.get("settings", {}).get("min_withdraw", MIN_WITHDRAW))
    if bal < min_wd:
        await update.message.reply_text(
            f"❌ Min withdraw ₹{min_wd:.0f}\n💰 Balance: ₹{bal:.0f}"
        )
        return
    B = InlineKeyboardButton
    kb = InlineKeyboardMarkup([
        [B("🇮🇳 UPI", callback_data="wd_method_upi")],
        [B("💛 CWallet", callback_data="wd_method_cwallet")],
        [B("🤖 @cctip_bot", callback_data="wd_method_cctip")],
        [B("💎 Crypto", callback_data="wd_method_crypto")],
    ])
    await update.message.reply_text(
        f"⬆️ <b>Withdraw</b>\n"
        f"💰 Balance: ₹{bal:.0f}\n"
        f"Min ₹{min_wd:.0f}\n\n"
        f"Choose payout method:",
        parse_mode="HTML",
        reply_markup=kb,
    )


async def cmd_myid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load()
    uid = update.effective_user.id
    tag = "YES ✅" if is_owner(data, uid) else "NO"
    await update.message.reply_text(f"🆔 `{uid}`\nOwner: *{tag}*", parse_mode="Markdown")


async def cmd_invite(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load()
    u = ensure_user(data, update.effective_user)
    me = await context.bot.get_me()
    link = f"https://t.me/{me.username}?start={u.get('ref_code')}"
    await update.message.reply_text(
        f"🔗 Invite link:\n`{link}`\n\n"
        f"Per referral (on their *1st deposit*):\n"
        f"• ₹{int(REFERRAL_BONUS)} flat\n"
        f"• +{int(REFERRAL_DEPOSIT_PCT*100)}% of deposit\n\n"
        f"Your refs: {int(u.get('referrals', 0) or 0)}\n"
        f"Earnings: ₹{float(u.get('ref_earnings', 0) or 0):.0f}",
        parse_mode="Markdown",
    )


async def cmd_mystats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load()
    user = update.effective_user
    u = ensure_user(data, user)
    avatar = None
    try:
        photos = await context.bot.get_user_profile_photos(user.id, limit=1)
        if photos.total_count > 0:
            f = await context.bot.get_file(photos.photos[0][-1].file_id)
            avatar = f"av_{user.id}.jpg"
            await f.download_to_drive(avatar)
    except Exception as e:
        logger.warning("avatar %s", e)
    try:
        path = make_stats_card(user, u, data, avatar_path=avatar)
        await update.message.reply_photo(
            photo=open(path, "rb"),
            caption=f"HR Casino Report · {user.first_name}",
        )
    except Exception as e:
        logger.warning("stats card %s", e)
        bal = float(u.get("balance", 0))
        await update.message.reply_text(
            f"Player Report\n{user.first_name}\nBalance: Rs {bal:.0f}\n"
            f"Games: {u.get('bets', 0)}\nWagered: Rs {float(u.get('wagered', 0)):.0f}"
        )


async def cmd_wagerstatus(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await cmd_mystats(update, context)



async def cmd_leaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load()
    user = update.effective_user
    ensure_user(data, user)
    avatar_map = {}
    try:
        items = sorted(
            data.get("users", {}).items(),
            key=lambda kv: float(kv[1].get("wagered", 0)),
            reverse=True,
        )[:5]
        for uid, _ in items:
            try:
                photos = await context.bot.get_user_profile_photos(int(uid), limit=1)
                if photos.total_count > 0:
                    f = await context.bot.get_file(photos.photos[0][-1].file_id)
                    p = f"av_lb_{uid}.jpg"
                    await f.download_to_drive(p)
                    avatar_map[uid] = p
            except Exception:
                pass
    except Exception as e:
        logger.warning("lb avatars %s", e)
    try:
        path_img = make_leaderboard_card(data, user.id, avatar_map=avatar_map)
        await update.message.reply_photo(
            photo=open(path_img, "rb"),
            caption="HR Casino · Wager Rankings",
        )
    except Exception as e:
        logger.warning("leaderboard card %s", e)
        items = sorted(
            data["users"].items(),
            key=lambda kv: float(kv[1].get("wagered", 0)),
            reverse=True,
        )[:10]
        lines = ["Top Wager Rankings"]
        for i2, (uid, u) in enumerate(items, 1):
            nm = u.get("username") or u.get("name") or uid
            lines.append(f"{i2}. {nm} — Rs {float(u.get('wagered', 0)):.0f}")
        await update.message.reply_text("\n".join(lines))


async def cmd_topwager(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load()
    user = update.effective_user
    ensure_user(data, user)
    try:
        path_img = make_leaderboard_card(data, user.id)
        await update.message.reply_photo(
            photo=open(path_img, "rb"),
            caption="🏆 HR Casino · Top Wager",
        )
    except Exception as e:
        logger.warning("topwager %s", e)
        items = sorted(data["users"].items(), key=lambda kv: float(kv[1].get("wagered", 0)), reverse=True)[:10]
        lines = ["🏆 Top Wager"]
        for i, (uid, u) in enumerate(items, 1):
            lines.append(f"{i}. {display_user(u, uid)} — ₹{float(u.get('wagered', 0)):.0f}")
        await update.message.reply_text("\n".join(lines))



async def send_low_balance(message, context, data, user, need=None):
    """Axom-style low balance + Deposit Now button."""
    me = await context.bot.get_me()
    bal = float((data.get("users") or {}).get(str(user.id), {}).get("balance", 0) or 0)
    kb = InlineKeyboardMarkup([[
        style_btn("⬇️ Deposit Now", style="primary", url=f"https://t.me/{me.username}?start=deposit"),
    ]])
    txt = "💵 Balance too low — top up to keep playing!"
    if need is not None:
        txt += f"\nNeed ₹{float(need):.0f} · You have ₹{bal:.0f}"
    try:
        await message.reply_text(txt, reply_markup=kb)
    except Exception:
        await message.reply_text(txt)


async def cmd_bonus(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🎁 Bonus: admin decide / loss refund manual.")


async def cmd_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Only owner/admin can cancel bets (prevent refund abuse)."""
    data = load()
    user = update.effective_user
    if not is_owner(data, user.id):
        await update.message.reply_text("⛔ Only admin can cancel matches.")
        return
    args = context.args or []
    # /cancel USER_ID  or reply to user
    target = None
    if update.message.reply_to_message and update.message.reply_to_message.from_user:
        target = str(update.message.reply_to_message.from_user.id)
    elif args:
        target = str(args[0]).strip()
    if not target:
        await update.message.reply_text("Usage: reply to player + /cancel\nOr: /cancel USER_ID")
        return
    refunded = []
    if target in data.get("pending_bets", {}):
        p = data["pending_bets"].pop(target)
        add_bal(data, target, float(p.get("stake", 0)))
        refunded.append(f"solo ₹{float(p.get('stake',0)):.0f}")
    for k, ch in list(data.get("pvp", {}).items()):
        if str(ch.get("a")) == target or str(ch.get("b")) == target:
            st = float(ch.get("stake", 0))
            if ch.get("locked"):
                if ch.get("a"):
                    add_bal(data, str(ch["a"]), st)
                if ch.get("b"):
                    add_bal(data, str(ch["b"]), st)
            data["pvp"].pop(k, None)
            refunded.append(f"pvp ₹{st:.0f}")
    save(data)
    if refunded:
        await update.message.reply_text(f"✅ Cancelled for `{target}`\n" + ", ".join(refunded), parse_mode="Markdown")
    else:
        await update.message.reply_text("Nothing pending for that user.")



async def ask_mode(update, context, game_key: str, stake: float, rule: str = None, rounds: int = 1):
    """rule: crazy (low wins) | normal (high wins) | None = ask"""
    if not await require_group(update, context):
        return
    data = load()
    if not await check_bot_and_game(update, context, data, game_key):
        return
    user = update.effective_user
    u = ensure_user(data, user)

    # clear own unaccepted PvP challenges so /dice doesn't feel "stuck" in PvP
    for _pid, _ch in list(data.get("pvp", {}).items()):
        if _ch.get("a") == user.id and _ch.get("status") == "wait_accept":
            data["pvp"].pop(_pid, None)
    save(data)
    mn = min_bet_val(data)
    mx = float(data["settings"].get("max_bet", MAX_BET))
    if stake < mn or stake > mx:
        await update.message.reply_text(f"Stake ₹{mn}–₹{mx}")
        return
    if float(u.get("balance", 0)) < stake:
        await send_low_balance(update.message, context, data, user, need=stake)
        return
    emoji, label = GAMES.get(game_key, ("🎲", game_key))
    if rule not in ("crazy", "normal"):
        kb = InlineKeyboardMarkup([[
            style_btn("⚡ Crazy Mode", style="danger", callback_data=f"rule_crazy_{game_key}_{int(stake)}_{user.id}_{int(rounds or 1)}"),
            style_btn("📈 Normal Mode", style="primary", callback_data=f"rule_normal_{game_key}_{int(stake)}_{user.id}_{int(rounds or 1)}"),
        ]])
        await update.message.reply_text(
            f"<b>🎮 {label} • ₹{stake:.0f}" + (f" • {rounds}R" if (rounds or 1) > 1 else "") + "</b>\n\n"
            f"<blockquote>"
            f"⚡ Crazy = lower score wins\n"
            f"📈 Normal = higher score wins"
            f"</blockquote>\n\n"
            f"Choose a mode:",
            parse_mode="HTML",
            reply_markup=kb,
        )
        return
    kb = InlineKeyboardMarkup([[
        style_btn(f"🤖 Vs Bot", style="primary", callback_data=f"mode_bot_{rule}_{game_key}_{int(stake)}_{user.id}_{int(rounds or 1)}"),
        style_btn("⚔ Open PvP", style="success", callback_data=f"mode_pvp_{rule}_{game_key}_{int(stake)}_{user.id}_{int(rounds or 1)}"),
    ]])
    rule_txt = "lower score wins" if rule == "crazy" else "higher score wins"
    un = user.username or user.first_name or "Player"
    nl = chr(10)
    await reply_prem(update.message, [
        ("user",), f" {un}", nl,
        f"/{game_key} {int(stake)}", nl,
        ("game",), f" {label} ₹{int(stake)}", nl, nl,
        ("bot",), " Against Bot — play vs bot", nl,
        ("check",), " Accept PvP — another player joins",
    ], reply_markup=kb)


async def cmd_crazy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """ /crazy 50  or /crazy 50 basket — always crazy rule """
    args = list(context.args or [])
    stake = parse_amount(args) or 0
    game_key = "dice"
    for a in args:
        al = a.lower()
        if al in GAMES:
            game_key = al
    if not stake:
        await update.message.reply_text("Usage: `/crazy 50` ya `/crazy 50 basket`", parse_mode="Markdown")
        return
    await ask_mode(update, context, game_key, stake, rule="crazy")


async def cmd_game(update: Update, context: ContextTypes.DEFAULT_TYPE, game_key: str):
    """ /dart 20 · /dart 50 2 · /dart all 3d2w · /dart 50 crazy """
    args = list(context.args or [])
    data = load()
    user = update.effective_user
    ensure_user(data, user)
    stake, rounds, use_all = parse_stake_rounds(data, user.id, args)
    rule = "normal"
    for a in args:
        al = str(a).lower()
        if al in ("crazy", "cz"):
            rule = "crazy"
        elif al in ("normal", "norm"):
            rule = "normal"
    if not stake:
        nl = chr(10)
        emoji, label = GAMES.get(game_key, ("🎲", game_key))
        await reply_prem(update.message, [
            ("game",), f" {label}", nl, nl,
            "vs Bot:", nl,
            f"/{game_key} 50  — 1 round", nl,
            f"/{game_key} 50 3  — 3 rounds", nl, nl,
            "vs Player:", nl,
            f"/{game_key} @user 50", nl,
            f"/{game_key} @user 50 3", nl,
            f"(or reply/tag a user + /{game_key} 50)",
        ])
        return
    await ask_mode(update, context, game_key, stake, rule=rule, rounds=rounds)

# ---------- DiceGamble-style dice flow ----------
DICE_WIN_MULT = 1.92  # like DiceGamble screenshots


def _dice_mode_meta(mode: str) -> dict:
    """rolls_per_turn, points_to_win, crazy, label, desc"""
    m = (mode or "normal").lower()
    table = {
        "normal": dict(rolls=1, pts=2, crazy=False, label="Normal Mode",
                       desc="Roll 1 die each turn. Higher wins the point. First to 2 points."),
        "double": dict(rolls=2, pts=2, crazy=False, label="Double Roll",
                       desc="Similar to Normal, but you roll 2 dice in a row. Greater sum wins the point."),
        "triple": dict(rolls=3, pts=2, crazy=False, label="Triple Roll (NEW!)",
                       desc="Same as Double, but 3 dice. Greater sum of three digits wins the point."),
        "crazy": dict(rolls=1, pts=2, crazy=True, label="Crazy Mode",
                      desc="Lower score wins the point. First to 2 points."),
        "crazy_double": dict(rolls=2, pts=2, crazy=True, label="Crazy Double Roll",
                             desc="2 dice, lower sum wins the point."),
        "crazy_triple": dict(rolls=3, pts=2, crazy=True, label="Crazy Triple Roll (NEW!)",
                             desc="3 dice, lower sum wins the point."),
    }
    return table.get(m, table["normal"])


async def cmd_dice(update, context):
    """DiceGamble-style: /dice 50 | /dice all → mode picker → confirm → open match."""
    data = load()
    user = update.effective_user
    msg = update.effective_message
    if not msg:
        return
    if not await check_bot_and_game(update, context, data, "dice"):
        return
    u = ensure_user(data, user)
    args = list(context.args or [])
    stake, rounds, use_all = parse_stake_rounds(data, user.id, args)
    bal = float(u.get("balance", 0) or 0)
    if stake is None:
        await msg.reply_text(
            "🎲 <b>Dice</b>\n"
            "<blockquote>"
            "Usage:\n"
            "<code>/dice 50</code> — bet ₹50\n"
            "<code>/dice all</code> — bet full balance\n"
            "</blockquote>",
            parse_mode="HTML",
        )
        return
    mn, mx = min_bet_val(data), float(data["settings"].get("max_bet", MAX_BET))
    if stake < mn:
        await msg.reply_text(f"⚠️ Min bet ₹{mn:.0f}")
        return
    if stake > mx:
        stake = mx
    if bal < stake:
        await msg.reply_text(
            f"⚠️ Low balance (₹{bal:.0f}). Need ₹{stake:.0f}.\nUse /deposit",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("💰 Deposit", callback_data="menu_deposit"),
            ]]),
        )
        return
    # store pending stake choice
    data.setdefault("dice_setup", {})[str(user.id)] = {
        "stake": float(stake),
        "time": time.time(),
        "chat_id": update.effective_chat.id,
    }
    save(data)
    name = user.first_name or "Player"
    B = InlineKeyboardButton
    kb = InlineKeyboardMarkup([
        [B("Normal Mode", callback_data="dg_mode_normal")],
        [B("Double Roll", callback_data="dg_mode_double")],
        [B("Triple Roll (NEW!)", callback_data="dg_mode_triple")],
        [B("Crazy Mode", callback_data="dg_mode_crazy")],
        [B("Crazy Double Roll", callback_data="dg_mode_crazy_double")],
        [B("Crazy Triple Roll (NEW!)", callback_data="dg_mode_crazy_triple")],
        [B("ℹ️ Mode Guide", callback_data="dg_guide"), B("❌ Cancel", callback_data="dg_cancel")],
    ])
    await msg.reply_text(
        f"<blockquote>🎲 {name}\n/dice {'all' if use_all else f'{stake:.0f}'}</blockquote>\n"
        f"🎲 <b>Choose the game mode</b>",
        parse_mode="HTML",
        reply_markup=kb,
    )


async def cmd_basket(update, context):
    await cmd_game(update, context, "basket")


async def cmd_football(update, context):
    await cmd_game(update, context, "football")


async def cmd_bowl(update, context):
    await cmd_game(update, context, "bowl")


async def cmd_dart(update, context):
    await cmd_game(update, context, "dart")


async def cmd_slot(update, context):
    args = list(context.args or [])
    if not args:
        nl = chr(10)
        await reply_prem(update.message, [
            ("game",), " Slots", nl, nl,
            "vs Bot:", nl,
            "/slots 50  — 1 round", nl,
            "/slots 50 3  — 3 rounds", nl, nl,
            "vs Player:", nl,
            "/slots @user 50", nl,
            "/slots @user 50 3", nl,
            "(or reply/tag a user + /slots 50)",
        ])
        return
    await cmd_game(update, context, "slot")





async def cmd_7up(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """7 Up / 7 Down — sum of 2 dice.
    /7up 50 up | /7up 50 down | /7up 50 7
    """
    if not await require_group(update, context):
        return
    data = load()
    if not await check_bot_and_game(update, context, data, "7up"):
        return
    user = update.effective_user
    u = ensure_user(data, user)
    args = [a.lower() for a in (context.args or [])]
    pick = None
    for a in args:
        if a in ("up", "7up", "high"):
            pick = "up"
        elif a in ("down", "7down", "low"):
            pick = "down"
        elif a in ("7", "seven", "exact"):
            pick = "7"
    stake, rounds, use_all = parse_stake_rounds(data, user.id, args)
    mn = min_bet_val(data)
    mx = float(data["settings"].get("max_bet", MAX_BET))
    nl = chr(10)
    if stake is None or pick is None:
        await reply_prem(update.message, [
            ("dice",), " 7 Up / 7 Down", nl, nl,
            "Usage:", nl,
            "/7up 50 up — 8-12 · 1.96x", nl,
            "/7up 50 down — 2-6 · 1.96x", nl,
            "/7up 50 7 — exactly 7 · 5.33x", nl,
            "/7up all up — full balance on UP",
        ])
        return
    if stake < mn or stake > mx:
        await reply_prem(update.message, [("warn",), f" Stake ₹{mn:.0f}–₹{mx:.0f}"])
        return
    if float(u.get("balance", 0) or 0) < stake:
        await reply_prem(update.message, [("error",), " Low balance"])
        return
    if not take_bal(data, str(user.id), stake):
        return
    # roll 2 dice visually
    try:
        d1 = await update.message.reply_dice(emoji="🎲")
        await asyncio.sleep(3.2)
        d2 = await update.message.reply_dice(emoji="🎲")
        await asyncio.sleep(3.2)
        v1, v2 = int(d1.dice.value), int(d2.dice.value)
    except Exception:
        v1, v2 = secrets.randbelow(6) + 1, secrets.randbelow(6) + 1
    total = v1 + v2
    win = False
    mult = 0
    if pick == "up" and total >= 8:
        win, mult = True, 1.96
    elif pick == "down" and total <= 6:
        win, mult = True, 1.96
    elif pick == "7" and total == 7:
        win, mult = True, 5.33
    payout = round(stake * mult, 2) if win else 0
    if win:
        add_bal(data, str(user.id), payout)
    record(data, user.id, "7Up7Down", stake, win, payout)
    save(data)
    if win:
        await reply_prem(update.message, [
            ("dice",), " 7 Up / 7 Down", nl, nl,
            f"Rolled: {v1}+{v2} = {total}", nl,
            f"Pick: {pick.upper()}", nl, nl,
            ("trophy",), f" You win ₹{payout - stake:.0f}!", nl,
            ("money",), f" Balance: ₹{float(data['users'][str(user.id)]['balance']):.0f}",
        ])
    else:
        await reply_prem(update.message, [
            ("dice",), " 7 Up / 7 Down", nl, nl,
            f"Rolled: {v1}+{v2} = {total}", nl,
            f"Pick: {pick.upper()}", nl, nl,
            ("error",), f" You lost ₹{stake:.0f}", nl,
            ("money",), f" Balance: ₹{float(data['users'][str(user.id)]['balance']):.0f}",
        ])


async def finish_coin(message, context, data, user, stake, side):
    """Settle an unbiased coin flip."""
    uid = str(user.id)
    nl = chr(10)

    # 🪙 throw animation
    try:
        await message.reply_text("🪙")
        await asyncio.sleep(0.7)
        await message.reply_text("🪙 🪙")
        await asyncio.sleep(0.7)
        await message.reply_text("🪙 🪙 🪙  Flipping...")
        await asyncio.sleep(1.0)
    except Exception:
        pass

    result = secrets.choice(("heads", "tails"))

    win = result == side
    payout = round(stake * 1.85, 2) if win else 0
    if win:
        add_bal(data, uid, payout)
    record(data, user.id, "Coin Flip", stake, win, payout)
    save(data)

    face = "🪙 HEADS" if result == "heads" else "🪙 TAILS"
    pick = "🪙 HEADS" if side == "heads" else "🪙 TAILS"
    if win:
        parts = [
            ("coin",), " Coin Flip", nl, nl,
            "You picked: ", pick, nl,
            "Landed on: ", face, nl, nl,
            ("trophy",), f" YOU WIN  +₹{payout - stake:.0f}", nl,
            ("money",), f" Balance: ₹{float(data['users'][uid]['balance']):.0f}",
        ]
    else:
        parts = [
            ("coin",), " Coin Flip", nl, nl,
            "You picked: ", pick, nl,
            "Landed on: ", face, nl, nl,
            ("error",), f" YOU LOST  -₹{stake:.0f}", nl,
            ("money",), f" Balance: ₹{float(data['users'][uid]['balance']):.0f}",
        ]
    await reply_prem(message, parts)


async def cmd_coin(update, context):
    """Coin flip Heads / Tails vs bot — /coin 50 heads"""
    if not await require_group(update, context):
        return
    data = load()
    if not await check_bot_and_game(update, context, data, "coin"):
        return
    user = update.effective_user
    u = ensure_user(data, user)
    args = [a.lower() for a in (context.args or [])]
    side = None
    for a in args:
        if a in ("h", "head", "heads"):
            side = "heads"
        if a in ("t", "tail", "tails"):
            side = "tails"
    stake, rounds, use_all = parse_stake_rounds(data, user.id, args)
    mn = min_bet_val(data)
    mx = float(data["settings"].get("max_bet", MAX_BET))
    nl = chr(10)
    if stake is None:
        await reply_prem(update.message, [
            ("coin",), " Coin Flip", nl, nl,
            "Usage:", nl,
            "/coin 50 heads", nl,
            "/coin 50 tails", nl,
            "/coin all heads",
        ])
        return
    if stake < mn or stake > mx:
        await reply_prem(update.message, [("warn",), f" Stake ₹{mn:.0f}–₹{mx:.0f}"])
        return
    if side is None:
        kb = InlineKeyboardMarkup([[
            style_btn("🪙 Heads", style="success", callback_data=f"coinflip_heads_{int(stake)}_{user.id}"),
            style_btn("🪙 Tails", style="primary", callback_data=f"coinflip_tails_{int(stake)}_{user.id}"),
        ]])
        await reply_prem(update.message, [
            ("coin",), f" Coin Flip  ·  ₹{int(stake)}", nl,
            "Pick a side:",
        ], reply_markup=kb)
        return
    if float(u.get("balance", 0) or 0) < stake:
        await reply_prem(update.message, [("error",), " Low balance"])
        return
    if not take_bal(data, str(user.id), stake):
        return
    save(data)
    await finish_coin(update.message, context, data, user, stake, side)



# Dice Predict multipliers (more numbers = lower odds) — Rolex style
PREDICT_MULT = {
    # Rolex-style: more numbers = lower payout (max 5)
    1: 5.18,
    2: 2.88,
    3: 1.92,
    4: 1.44,
    5: 1.10,
}


async def cmd_predict(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /predict 50 1 3 5   — bet 50 on numbers 1,3,5 (max 5 numbers)
    /predict 100 6      — single number ~4.9x
    """
    if not await require_group(update, context):
        return
    data = load()
    if not await check_bot_and_game(update, context, data, "dr"):
        return
    user = update.effective_user
    u = ensure_user(data, user)
    args = context.args or []
    if len(args) < 2:
        await update.message.reply_text(
            "🎯 <b>Dice Predict</b>\n\n"
            "Pick 1–5 numbers (1–6). More picks = lower multiplier.\n\n"
            "<code>/predict 50 6</code> → 1 number · <b>5.18×</b>\n"
            "<code>/predict 50 1 2</code> → 2 numbers · <b>2.88×</b>\n"
            "<code>/predict 100 1 2 3</code> → 3 · <b>1.92×</b>\n"
            "<code>/predict 50 1 2 3 4</code> → 4 · <b>1.44×</b>\n"
            "<code>/predict 50 1 2 3 4 5</code> → 5 · <b>1.10×</b>\n"
            "Also: /dr high|low|odd|even · /dj 50 high\n\n"
            f"Min ₹{min_bet_val(data):.0f}",
            parse_mode="HTML",
        )
        return
    try:
        stake = float(args[0])
    except Exception:
        await update.message.reply_text("First arg = stake. Example: /predict 50 1 3 5")
        return
    nums = []
    for a in args[1:]:
        try:
            n = int(a)
            if 1 <= n <= 6 and n not in nums:
                nums.append(n)
        except Exception:
            pass
    if not nums or len(nums) > 5:
        await update.message.reply_text("Pick 1 to 5 unique numbers from 1–6.")
        return
    mn, mx = min_bet_val(data), float(data["settings"].get("max_bet", MAX_BET))
    if stake < mn or stake > mx:
        await update.message.reply_text(f"Stake ₹{mn:.0f}–₹{mx:.0f}")
        return
    if float(u.get("balance", 0)) < stake:
        await update.message.reply_text(f"❌ Low balance ₹{float(u.get('balance',0)):.0f}")
        return
    if not take_bal(data, str(user.id), stake):
        await update.message.reply_text("Low balance!")
        return
    save(data)
    mult = PREDICT_MULT.get(len(nums), 1.10)
    fair_id = "NV-" + "".join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(8))
    # bot rolls dice
    msg = await update.message.reply_dice(emoji="🎲")
    roll = int(msg.dice.value)
    win = roll in nums
    payout = round(stake * mult, 2) if win else 0.0
    if win:
        add_bal(data, str(user.id), payout)
        record(data, str(user.id), "predict", stake, True, payout)
        result_line = f"✅ WIN · ₹{payout:.2f} ({mult:.2f}x)"
    else:
        record(data, str(user.id), "predict", stake, False, 0)
        result_line = f"❌ LOSS · −₹{stake:.0f}"
    save(data)
    picks = " · ".join(str(n) for n in sorted(nums))
    await update.message.reply_text(
        f"🎯 <b>PREDICT</b>\n"
        f"<blockquote>"
        f"{result_line}\n"
        f"🎲 Roll: <b>{roll}</b>\n"
        f"Your pick: {picks}\n"
        f"Stake: ₹{stake:.0f} · Mult: {mult:.2f}x\n"
        f"Fair ID: <code>{fair_id}</code>"
        f"</blockquote>",
        parse_mode="HTML",
    )


async def cmd_dj(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Dice Jack — two dice totals.
    /dj 50 high  — total 7+ wins ~1.9x
    /dj 50 low   — total 2–6 wins ~1.9x
    /dj 50 7     — exact 7 pays ~4.5x
    """
    if not await require_group(update, context):
        return
    data = load()
    if not await check_bot_and_game(update, context, data, "dice"):
        return
    user = update.effective_user
    u = ensure_user(data, user)
    args = [a.lower() for a in (context.args or [])]
    if len(args) < 2:
        await update.message.reply_text(
            "🃏 <b>Dice Jack (DJ)</b>\n\n"
            "<code>/dj 50 high</code> — total ≥ 7 · 1.90x\n"
            "<code>/dj 50 low</code> — total ≤ 6 · 1.90x\n"
            "<code>/dj 50 7</code> — exact total 7 · 4.50x\n"
            "<code>/dj 100 12</code> — exact 12 · 30x",
            parse_mode="HTML",
        )
        return
    try:
        stake = float(args[0])
    except Exception:
        await update.message.reply_text("Example: /dj 50 high")
        return
    mode = args[1]
    mn, mx = min_bet_val(data), float(data["settings"].get("max_bet", MAX_BET))
    if stake < mn or stake > mx:
        await update.message.reply_text(f"Stake ₹{mn:.0f}–₹{mx:.0f}")
        return
    if float(u.get("balance", 0)) < stake:
        await update.message.reply_text("Low balance!")
        return
    if not take_bal(data, str(user.id), stake):
        await update.message.reply_text("Low balance!")
        return
    save(data)
    d1 = await update.message.reply_dice(emoji="🎲")
    await asyncio.sleep(0.4)
    d2 = await update.message.reply_dice(emoji="🎲")
    v1, v2 = int(d1.dice.value), int(d2.dice.value)
    total = v1 + v2
    mult = 0.0
    win = False
    if mode in ("high", "h"):
        win = total >= 7
        mult = 1.90
        label = "HIGH (≥7)"
    elif mode in ("low", "l"):
        win = total <= 6
        mult = 1.90
        label = "LOW (≤6)"
    else:
        try:
            target = int(mode)
        except Exception:
            add_bal(data, str(user.id), stake)  # refund
            save(data)
            await update.message.reply_text("Mode: high / low / or exact total 2–12")
            return
        if target < 2 or target > 12:
            add_bal(data, str(user.id), stake)
            save(data)
            await update.message.reply_text("Exact total must be 2–12")
            return
        win = total == target
        # rough odds by ways
        ways = {2:1,3:2,4:3,5:4,6:5,7:6,8:5,9:4,10:3,11:2,12:1}
        mult = round(min(30.0, (36 / max(1, ways.get(target, 1))) * 0.95), 2)
        label = f"EXACT {target}"
    fair_id = "DJ-" + "".join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(8))
    if win:
        payout = round(stake * mult, 2)
        add_bal(data, str(user.id), payout)
        record(data, str(user.id), "dj", stake, True, payout)
        res = f"✅ WIN · ₹{payout:.2f} ({mult:.2f}x)"
    else:
        record(data, str(user.id), "dj", stake, False, 0)
        res = f"❌ LOSS · −₹{stake:.0f}"
    save(data)
    await update.message.reply_text(
        f"🃏 <b>DICE JACK</b>\n"
        f"<blockquote>"
        f"{res}\n"
        f"🎲 {v1} + {v2} = <b>{total}</b>\n"
        f"Bet: {label}\n"
        f"Stake: ₹{stake:.0f}\n"
        f"Fair ID: <code>{fair_id}</code>"
        f"</blockquote>",
        parse_mode="HTML",
    )



async def cmd_dr(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Dice Roulette vs bot.
    /dr high 50 · /dr low 50 · /dr odd 50 · /dr even 50 · /dr all high
    """
    if not await require_group(update, context):
        return
    data = load()
    if not await check_bot_and_game(update, context, data, "dr"):
        return
    user = update.effective_user
    u = ensure_user(data, user)
    args = [a.lower() for a in (context.args or [])]
    mode = None
    for a in args:
        if a in ("high", "low", "odd", "even"):
            mode = a
    stake, rounds, use_all = parse_stake_rounds(data, user.id, args)
    mn = min_bet_val(data)
    mx = float(data["settings"].get("max_bet", MAX_BET))
    if stake is None:
        await update.message.reply_text(
            f"{ce('zap','⚡')} <b>Dice Roulette</b>\n"
            f"<code>/dr high 50</code> — 4•5•6\n"
            f"<code>/dr low 50</code> — 1•2•3\n"
            f"<code>/dr odd 50</code> — 1•3•5\n"
            f"<code>/dr even 50</code> — 2•4•6\n"
            f"<code>/dr all high</code> — full balance",
            parse_mode="HTML",
        )
        return
    if stake < mn or stake > mx:
        await update.message.reply_text(f"Stake ₹{mn:.0f}–₹{mx:.0f}")
        return
    if mode is None:
        kb = InlineKeyboardMarkup([
            [
                style_btn("📈 HIGH", style="success", callback_data=f"drpick_high_{int(stake)}_{user.id}"),
                style_btn("📉 LOW", style="primary", callback_data=f"drpick_low_{int(stake)}_{user.id}"),
            ],
            [
                style_btn("1️⃣ ODD", style="primary", callback_data=f"drpick_odd_{int(stake)}_{user.id}"),
                style_btn("2️⃣ EVEN", style="success", callback_data=f"drpick_even_{int(stake)}_{user.id}"),
            ],
        ])
        await reply_prem(update.message, [
            ("dice",), f" Dice Roulette  ·  ₹{stake:.0f}", chr(10),
            "Choose mode:",
        ], reply_markup=kb)
        return
    if float(u.get("balance", 0)) < stake:
        await update.message.reply_text(
            f"❌ Low balance! ₹{float(u.get('balance', 0)):.0f}"
        )
        return
    if not take_bal(data, str(user.id), stake):
        await update.message.reply_text("Low balance!")
        return
    save(data)
    await _finish_dr(update, context, data, user, stake, mode)


async def _finish_dr(update, context, data, user, stake, mode):
    labels = {
        "high": "HIGH (4•5•6)",
        "low": "LOW (1•2•3)",
        "odd": "ODD (1•3•5)",
        "even": "EVEN (2•4•6)",
    }
    pick = labels.get(mode, mode.upper())
    bid = rid()
    target = update.message or update.callback_query.message
    try:
        await reply_prem(target, [
            ("dice",), f" Dice Roulette #{bid}  ·  ₹{stake:.0f}", chr(10),
            ("target",), f" Pick: {pick}", chr(10),
            "Rolling...",
        ])
    except Exception:
        await target.reply_text(f"🎲 Dice Roulette #{bid} · ₹{stake:.0f}\n🎯 Pick: {pick}\nRolling...")
    dice_msg = await target.reply_dice(emoji="🎲")
    value = dice_msg.dice.value
    await asyncio.sleep(3.5)
    if mode == "high":
        win = value >= 4
    elif mode == "low":
        win = value <= 3
    elif mode == "odd":
        win = value % 2 == 1
    else:
        win = value % 2 == 0
    payout = round(stake * 1.85, 2) if win else 0
    uid = str(user.id)
    if win:
        add_bal(data, uid, payout)
    record(data, user.id, "Dice Roulette", stake, win, payout)
    save(data)
    nl = chr(10)
    delta = f"+₹{payout - stake:.0f}" if win else f"-₹{stake:.0f}"
    parts = [
        ("dice",), f" Dice Roulette #{bid}", nl,
        f"Rolled: {value}  |  Pick: {pick}", nl,
        (("trophy",) if win else ("error",)),
        (" YOU WON  " if win else " YOU LOST  ") + delta, nl,
        ("money",), f" Balance: ₹{float(data['users'][uid]['balance']):.0f}",
    ]
    try:
        await reply_prem(target, parts)
    except Exception:
        result = "🏆 YOU WON" if win else "❌ YOU LOST"
        await target.reply_text(
            f"🎲 Dice Roulette #{bid}\n"
            f"Rolled: {value} | Pick: {pick}\n"
            f"{result}  {delta}\n"
            f"💰 Balance: ₹{float(data['users'][uid]['balance']):.0f}"
        )



async def cmd_battle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_group(update, context):
        return
    data = load()
    user = update.effective_user
    u = ensure_user(data, user)
    target = find_target(update, context.args)
    stake = parse_amount(context.args) or 50
    if not target or target == user.id:
        await update.message.reply_text("Usage: /battle @user 50  or reply + /battle 50")
        return
    if float(u.get("balance", 0)) < stake:
        await update.message.reply_text("Low balance!")
        return
    ensure_user(data, type("U", (), {"id": target, "username": "", "first_name": "Player"})())
    # fix ensure for target - already may exist
    if str(target) not in data["users"]:
        data["users"][str(target)] = {
            "balance": 0, "ref_code": rid("R"), "referrals": 0,
            "wagered": 0, "won": 0, "lost": 0, "bets": 0, "username": "", "name": "",
        }
        save(data)
    pid = rid()
    data.setdefault("pvp", {})[pid] = {
        "id": pid,
        "game": "dice",
        "emoji": "🎲",
        "stake": stake,
        "a": user.id,
        "b": target,
        "a_val": None,
        "b_val": None,
        "locked": False,
        "status": "wait_accept",
        "time": time.time(),
    }
    save(data)
    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Accept Crazy PvP", callback_data=f"pvp_acc_{pid}"),
        InlineKeyboardButton("❌ Decline", callback_data=f"pvp_dec_{pid}"),
    ]])
    await update.message.reply_text(
        f"⚔️ *Crazy PvP Challenge* #{pid}\n"
        f"{user.first_name} challenges you!\n"
        f"Stake: ₹{stake:.0f} each\n"
        f"Rule: *lower score wins*\n\n"
        f"Accept karein:",
        parse_mode="Markdown",
        reply_markup=kb,
    )


# ---------- RPS / Mines simple vs bot ----------
async def cmd_rps(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_group(update, context):
        return
    data = load()
    if not await check_bot_and_game(update, context, data, "rps"):
        return
    u = ensure_user(data, update.effective_user)
    stake = parse_amount(context.args) or 0
    if not stake or float(u.get("balance", 0)) < stake:
        await update.message.reply_text("Usage: `/rps 50` (need balance)", parse_mode="Markdown")
        return
    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("🪨", callback_data=f"rps_rock_{int(stake)}"),
        InlineKeyboardButton("📄", callback_data=f"rps_paper_{int(stake)}"),
        InlineKeyboardButton("✂️", callback_data=f"rps_scissors_{int(stake)}"),
    ]])
    await update.message.reply_text(f"✂️ RPS • ₹{stake:.0f}", reply_markup=kb)


async def cmd_mines(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """5x5 Mines — pick safe tiles, avoid bombs."""
    if not await require_group(update, context):
        return
    data = load()
    if not await check_bot_and_game(update, context, data, "mines"):
        return
    user = update.effective_user
    u = ensure_user(data, user)
    stake = parse_amount(context.args) or 0
    mn = float(data["settings"].get("min_bet", MIN_BET))
    nl = chr(10)
    if not stake or stake < mn:
        await reply_prem(update.message, [
            ("bomb",), " Mines", nl, nl,
            "Usage: /mines 50", nl,
            "5x5 grid · avoid the bombs · cash out anytime",
        ])
        return
    if float(u.get("balance", 0) or 0) < stake:
        await reply_prem(update.message, [("error",), " Low balance"])
        return
    if not take_bal(data, str(user.id), stake):
        return
    # Every round uses a disclosed, fixed count; balance and admin settings do not affect it.
    n_bombs = 5
    bombs = set(secrets.SystemRandom().sample(range(1, 26), n_bombs))
    data.setdefault("mines_games", {})[str(user.id)] = {
        "stake": stake,
        "bombs": list(bombs),
        "revealed": [],
        "mult": 1.0,
        "alive": True,
    }
    save(data)
    rows = []
    for r in range(5):
        row = []
        for c in range(5):
            n = r * 5 + c + 1
            row.append(InlineKeyboardButton("⬜", callback_data=f"mine25_{n}_{user.id}"))
        rows.append(row)
    rows.append([style_btn("💰 Cash Out", style="success", callback_data=f"minecash_{user.id}")])
    kb = InlineKeyboardMarkup(rows)
    await reply_prem(update.message, [
        ("bomb",), f" Mines • ₹{int(stake)}", nl,
        "Grid 5×5 · bombs loaded", nl,
        "Tap tiles · Cash out before a bomb!",
    ], reply_markup=kb)


async def cmd_jackpot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load()
    pool = float(data.get("jackpot_pool", 0) or 0)
    jp = data.setdefault("jackpot", {"pool": pool, "joined": [], "last_winners": [], "draw_hour": 21})
    joined = jp.get("joined") or []
    players = len(data.get("users") or {})
    kb = InlineKeyboardMarkup([[
        style_btn("Join Jackpot", style="success", callback_data="jp_join"),
        style_btn("How?", style="success", callback_data="jp_how"),
    ]])
    last = jp.get("last_winners") or []
    last_txt = ", ".join(last[:3]) if last else "—"
    nl = chr(10)
    parts = [
        ("gift",), " Current Pool: ₹{:.0f}".format(pool), nl,
        ("user",), " Players: {}".format(players), nl,
        ("check",), " Joined: {}".format(len(joined)), nl,
        ("chart",), " Contribution: 0.1% of every bet", nl,
        ("bell",), " Min to draw: ₹100", nl,
        ("time",), " Auto draw at: 21:00", nl, nl,
        ("trophy",), " Last Winner: ", last_txt, nl, nl,
        ("rocket",), " Every bet adds 0.1% to the jackpot pool!",
    ]
    await reply_prem(update.message, parts, reply_markup=kb)


async def cmd_jackpotdraw(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load()
    if not is_owner(data, update.effective_user.id):
        await update.message.reply_text("Owner only")
        return
    jp = data.setdefault("jackpot", {"joined": [], "pool": 0})
    joined = list(jp.get("joined") or [])
    pool = float(data.get("jackpot_pool", 0))
    if pool < 1 or not joined:
        await update.message.reply_text("Pool/joined empty")
        return
    # pick up to 3 winners
    n = min(3, len(joined))
    winners = secrets.SystemRandom().sample(joined, n)
    share = round(pool / n, 2)
    names = []
    for w in winners:
        add_bal(data, w, share)
        un = data["users"].get(w, {}).get("name") or w
        names.append(f"{un} ₹{share:.0f}")
    data["jackpot_pool"] = 0.0
    jp["pool"] = 0.0
    jp["joined"] = []
    jp["last_winners"] = names
    save(data)
    await update.message.reply_text(
        f"🏆 JACKPOT DRAW\nPool was ₹{pool:.0f}\n" + "\n".join(names)
    )



async def cmd_cutbal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """ /cutbal @user 50  or reply + /cutbal 50 — owner/admin cuts balance """
    data = load()
    admin = update.effective_user
    admins = set(data.get("bot_admins", []) or [])
    if not (is_owner(data, admin.id) or admin.id in admins):
        await update.message.reply_text("👑 Owner / Admin only")
        return
    target = find_target(update, context.args)
    amount = parse_amount(context.args)
    if not target or not amount or amount <= 0:
        await update.message.reply_text(
            "✂️ *Cut balance*\n"
            "Usage:\n"
            "`/cutbal @user 50`\n"
            "ya message reply karke `/cutbal 50`",
            parse_mode="Markdown",
        )
        return
    uid = str(target)
    if uid not in data.get("users", {}):
        await update.message.reply_text("User bot mein registered nahi (pehle /start karwao)")
        return
    bal = float(data["users"][uid].get("balance", 0))
    cut = min(bal, float(amount))
    if cut <= 0:
        await update.message.reply_text("User ka balance already 0")
        return
    data["users"][uid]["balance"] = round(bal - cut, 2)
    save(data)
    uname = data["users"][uid].get("name") or data["users"][uid].get("username") or uid
    await update.message.reply_text(
        f"✂️ Cut *₹{cut:.0f}* from `{uname}`\n"
        f"New balance: *₹{data['users'][uid]['balance']:.0f}*",
        parse_mode="Markdown",
    )
    try:
        await context.bot.send_message(
            int(target),
            f"⚠️ Admin ne aapka *₹{cut:.0f}* balance cut kiya.\nNew bal: *₹{data['users'][uid]['balance']:.0f}*",
            parse_mode="Markdown",
        )
    except Exception:
        pass


async def cmd_hb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """House balance in USD + premium emoji (no jackpot line)."""
    data = load()
    status = "Active — Bets Allowed!" if data.get("settings", {}).get("bot_on", True) else "Paused"
    hb_inr = float(data.get("settings", {}).get("house_balance", 0) or 0)
    rates = data.get("settings", {}).get("rates") or DEFAULT_RATES
    usd_rate = float(rates.get("USD", 84) or 84)  # 1 USD ≈ N INR
    hb_usd = hb_inr / usd_rate if usd_rate else 0
    nl = chr(10)
    parts = [
        ("bank",), ("dollar",), " HR CASINO · House Bank", nl, nl,
        ("money",), f" House balance: ${hb_usd:,.2f} USD", nl,
        ("check",) if "Active" in status else ("warn",), f" {status}", nl,
    ]
    try:
        await reply_prem(update.message, parts)
    except Exception:
        await update.message.reply_text(
            f"🏦 HR CASINO · House\nHouse balance: ${hb_usd:,.2f} USD\n{status}"
        )


async def cmd_hbadd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Owner only · DM only: /hbadd 1000 or /hbadd -500"""
    if update.effective_chat and update.effective_chat.type != "private":
        await update.message.reply_text("🔒 /hbadd only works in bot DM.")
        return
    data = load()
    if not is_owner(data, update.effective_user.id):
        await update.message.reply_text("👑 Owner only")
        return
    if not context.args:
        hb = float(data.get("settings", {}).get("house_balance", 0) or 0)
        rates = data.get("settings", {}).get("rates") or DEFAULT_RATES
        usd_rate = float(rates.get("USD", 84) or 84)
        await update.message.reply_text(
            f"House: ${hb / usd_rate:,.2f} USD (₹{hb:,.2f})\n"
            f"Usage: /hbadd 1000  or  /hbadd -200\n"
            f"(amounts in INR internal)"
        )
        return
    try:
        delta = float(context.args[0].replace(",", ""))
    except Exception:
        await update.message.reply_text("Example: /hbadd 1000")
        return
    data.setdefault("settings", {})
    cur = float(data["settings"].get("house_balance", 0) or 0)
    data["settings"]["house_balance"] = round(cur + delta, 2)
    save(data)
    try:
        log_admin(update.effective_user.id, "hbadd", f"delta={delta} new={data['settings']['house_balance']}")
    except Exception:
        pass
    rates = data.get("settings", {}).get("rates") or DEFAULT_RATES
    usd_rate = float(rates.get("USD", 84) or 84)
    new_hb = data["settings"]["house_balance"]
    await update.message.reply_text(
        f"✅ House: ${cur / usd_rate:,.2f} → <b>${new_hb / usd_rate:,.2f} USD</b>\n"
        f"(₹{cur:,.0f} → ₹{new_hb:,.0f})",
        parse_mode="HTML",
    )


async def cmd_setwallet(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load()
    user = update.effective_user
    u = ensure_user(data, user)
    if not context.args:
        cur = u.get("payout_upi") or "not set"
        await update.message.reply_text(f"Current payout UPI: {cur}\nUsage: /setwallet name@upi")
        return
    upi = context.args[0].strip()
    u["payout_upi"] = upi
    save(data)
    await update.message.reply_text(f"✅ Payout wallet saved: <code>{upi}</code>", parse_mode="HTML")



async def cmd_creditbyamount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Owner: /creditbyamount 300.47 — match unique UPI amount and credit base deposit."""
    data = load()
    if not is_owner(data, update.effective_user.id):
        return
    if not context.args:
        await update.message.reply_text("Usage: /creditbyamount 300.47\n(paste exact amount from UPI notification)")
        return
    try:
        amt = float(context.args[0].replace(",", ""))
    except Exception:
        await update.message.reply_text("Invalid amount")
        return
    key = f"{amt:.2f}"
    entry = (data.get("upi_unique") or {}).get(key)
    if not entry or entry.get("status") != "waiting":
        # fuzzy search
        entry = None
        key = None
        for k, v in (data.get("upi_unique") or {}).items():
            if v.get("status") == "waiting" and abs(float(v.get("unique_amt", 0)) - amt) < 0.001:
                entry, key = v, k
                break
    if not entry:
        await update.message.reply_text("No waiting deposit for that amount.")
        return
    uid = str(entry["uid"])
    base = float(entry.get("amount") or amt)
    ensure_user(data, type("U", (), {"id": int(uid), "username": None, "first_name": uid})())
    add_bal(data, uid, base)
    data["upi_unique"][key]["status"] = "credited"
    data.get("pending_dep_step", {}).pop(uid, None)
    u = data["users"][uid]
    u["wager_need"] = float(u.get("wager_need", 0) or 0) + base
    ref_pay = apply_referral_first_deposit(data, uid, base)
    save(data)
    extra = f"\n🎁 Referrer +₹{ref_pay:.0f} (₹10 + 20%)" if ref_pay else ""
    await update.message.reply_text(
        f"✅ Credited ₹{base:.0f} → user `{uid}` (paid ₹{amt:.2f}){extra}",
        parse_mode="Markdown",
    )
    try:
        await context.bot.send_message(
            int(uid),
            f"✅ <b>Deposit approved</b>\n+₹{base:.0f} credited.\nWager requirement +₹{base:.0f} (1×).",
            parse_mode="HTML",
        )
    except Exception:
        pass
    if ref_pay:
        try:
            ref_id = data["users"][uid].get("referred_by")
            await context.bot.send_message(
                int(ref_id),
                f"🎁 <b>Referral reward</b>\n"
                f"Your invite made 1st deposit ₹{base:.0f}\n"
                f"You got <b>₹{ref_pay:.0f}</b> (₹10 + 20%).",
                parse_mode="HTML",
            )
        except Exception:
            pass


async def cmd_setbinanceaddr(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load()
    if not is_owner(data, update.effective_user.id):
        return
    if not context.args:
        cur = data.get("settings", {}).get("binance_address", "")
        await update.message.reply_text(f"Current: {cur or 'not set'}\nUsage: /setbinanceaddr TXxxxx...")
        return
    addr = context.args[0].strip()
    data.setdefault("settings", {})["binance_address"] = addr
    save(data)
    await update.message.reply_text(f"✅ Binance address set:\n<code>{addr}</code>", parse_mode="HTML")


async def cmd_boton(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load()
    uid = update.effective_user.id
    if not is_owner(data, uid) and uid not in set(data.get("bot_admins") or []):
        await update.message.reply_text("👑 Owner / Admin only")
        return
    data.setdefault("settings", {})["bot_on"] = True
    save(data)
    await update.message.reply_text("✅ <b>Bot ON</b> — all games enabled.", parse_mode="HTML")


async def cmd_botoff(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load()
    uid = update.effective_user.id
    if not is_owner(data, uid) and uid not in set(data.get("bot_admins") or []):
        await update.message.reply_text("👑 Owner / Admin only")
        return
    data.setdefault("settings", {})["bot_on"] = False
    save(data)
    await update.message.reply_text("⏸ <b>Bot OFF</b> — maintenance mode.", parse_mode="HTML")


async def _auto_resume_after(seconds: int = 240):
    """Background: wait then turn bot_on back True (self-heal window)."""
    try:
        await asyncio.sleep(max(60, int(seconds)))
        data = load()
        data.setdefault("settings", {})["bot_on"] = True
        data["settings"]["fixbot_until"] = 0
        save(data)
        logger.info("fixbot: auto resume ON after %ss", seconds)
        # notify owners
        for oid in owners(data):
            try:
                from telegram import Bot
                bot = Bot(BOT_TOKEN)
                await bot.send_message(
                    oid,
                    "✅ <b>Auto-maintenance complete</b>\nBot is <b>ON</b> again. Stuck matches cleared.",
                    parse_mode="HTML",
                )
            except Exception:
                pass
    except Exception as e:
        logger.warning("auto_resume failed: %s", e)


def run_self_heal(data) -> dict:
    """Clear stuck state — does not rewrite code, stabilizes runtime."""
    stats = {"bets": 0, "deps": 0, "tips": 0, "binance": 0}
    now = time.time()
    # stuck pending bets > 10 min
    pb = data.get("pending_bets") or {}
    dead = []
    for pid, p in list(pb.items()):
        age = now - float(p.get("time") or p.get("created") or 0)
        if age > 600 or p.get("settling"):
            dead.append(pid)
    for pid in dead:
        pb.pop(pid, None)
        stats["bets"] += 1
    data["pending_bets"] = pb
    # old deposit steps > 2h
    pds = data.get("pending_dep_step") or {}
    for uid, dep in list(pds.items()):
        if now - float(dep.get("created") or 0) > 7200:
            pds.pop(uid, None)
            stats["deps"] += 1
    data["pending_dep_step"] = pds
    # tips
    tips = data.get("pending_tips") or {}
    for k, t in list(tips.items()):
        if now - float(t.get("time") or 0) > 3600:
            tips.pop(k, None)
            stats["tips"] += 1
    data["pending_tips"] = tips
    # binance waiting > 2h
    bn = data.get("pending_binance") or {}
    for uid, b in list(bn.items()):
        if b.get("status") == "waiting" and now - float(b.get("time") or 0) > 7200:
            bn.pop(uid, None)
            stats["binance"] += 1
    data["pending_binance"] = bn
    return stats


async def cmd_fixbot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Owner: /fixbot [minutes]
    Puts bot in maintenance, clears stuck matches, auto-ON after 3–5 min.
    This is self-heal — not AI rewriting source code.
    """
    data = load()
    uid = update.effective_user.id
    if not is_owner(data, uid):
        await update.message.reply_text("👑 Owner only")
        return
    minutes = 4
    if context.args:
        try:
            minutes = max(3, min(15, int(float(context.args[0]))))
        except Exception:
            minutes = 4
    seconds = minutes * 60

    data.setdefault("settings", {})["bot_on"] = False
    data["settings"]["fixbot_until"] = time.time() + seconds
    stats = run_self_heal(data)
    save(data)

    await update.message.reply_text(
        f"🛠 <b>AUTO MAINTENANCE</b>\n"
        f"<blockquote>"
        f"Bot paused for <b>{minutes} min</b>\n"
        f"Cleared stuck bets: {stats['bets']}\n"
        f"Cleared old deposits: {stats['deps']}\n"
        f"Cleared tips: {stats['tips']}\n"
        f"Cleared binance waits: {stats['binance']}\n\n"
        f"Auto <b>ON</b> after {minutes} minutes.\n"
        f"Force open now: /boton\n"
        f"</blockquote>\n"
        f"<i>Note: This stabilizes the bot. It does not rewrite code like an AI.</i>",
        parse_mode="HTML",
    )
    # background resume
    try:
        asyncio.create_task(_auto_resume_after(seconds))
    except Exception as e:
        logger.warning("create_task resume: %s", e)


async def cmd_setminibet(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load()
    uid = update.effective_user.id
    admins = set(data.get("bot_admins", []) or [])
    if not (is_owner(data, uid) or uid in admins):
        await update.message.reply_text("👑 Owner / Admin only")
        return
    if not context.args:
        await update.message.reply_text(
            f"Current min bet: <b>₹{min_bet_val(data):.0f}</b>\nUsage: <code>/setminibet 300</code>",
            parse_mode="HTML",
        )
        return
    try:
        v = float(context.args[0])
        if v < 1:
            raise ValueError()
    except Exception:
        await update.message.reply_text("Invalid amount. Example: /setminibet 300")
        return
    data.setdefault("settings", {})["min_bet"] = v
    save(data)
    await update.message.reply_text(f"✅ Min bet set to <b>₹{v:.0f}</b>", parse_mode="HTML")


async def cmd_setmaxbet(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Owner/Admin: /setmaxbet 5000 — raise maximum bet."""
    data = load()
    uid = update.effective_user.id
    admins = set(data.get("bot_admins", []) or [])
    if not (is_owner(data, uid) or uid in admins):
        await update.message.reply_text("👑 Owner / Admin only")
        return
    cur = float(data.get("settings", {}).get("max_bet", MAX_BET))
    if not context.args:
        await update.message.reply_text(
            f"Current max bet: <b>₹{cur:,.0f}</b>\nUsage: <code>/setmaxbet 10000</code>",
            parse_mode="HTML",
        )
        return
    try:
        v = float(context.args[0].replace(",", ""))
        if v < 1:
            raise ValueError()
    except Exception:
        await update.message.reply_text("Invalid amount. Example: /setmaxbet 10000")
        return
    data.setdefault("settings", {})["max_bet"] = v
    save(data)
    await update.message.reply_text(f"✅ Max bet set to <b>₹{v:,.0f}</b>", parse_mode="HTML")


async def cmd_addgatewayupi(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Owner: /addgatewayupi gpay KEY SECRET
    Or /addgatewayupi gpay  — uses built-in merchant A801 after portal API key.
    """
    data = load()
    if not is_owner(data, update.effective_user.id):
        await update.message.reply_text("👑 Owner only")
        return
    if not context.args:
        # seed GPay.one merchant defaults
        data.setdefault("settings", {})["gateway_upi"] = {
            "provider": "gpay.one",
            "merchant_id": GPAY_MERCHANT_ID,
            "password": GPAY_MERCHANT_PASS,
            "api_base": GPAY_API_BASE,
            "portal": GPAY_PORTAL,
            "key": (data.get("settings") or {}).get("gateway_upi", {}).get("key") or "",
            "secret": (data.get("settings") or {}).get("gateway_upi", {}).get("secret") or "",
            "enabled": True,
            "updated": time.time(),
        }
        save(data)
        await update.message.reply_text(
            f"🇮🇳 <b>GPay.one gateway seeded</b>\n\n"
            f"Merchant ID: <code>{GPAY_MERCHANT_ID}</code>\n"
            f"Portal: {GPAY_PORTAL}\n"
            f"API: {GPAY_API_BASE}\n\n"
            f"<b>Next (portal se):</b>\n"
            f"1. Login → password change\n"
            f"2. Server IP whitelist\n"
            f"3. API Key + Secret copy\n"
            f"4. <code>/setgatewaykey YOUR_KEY</code>\n"
            f"5. <code>/setgatewaysecret YOUR_SECRET</code>\n"
            f"6. <code>/gatewaystatus</code>\n\n"
            f"Docs password (showdoc): AstroPay\n"
            f"Until key+webhook live: unique UPI + /creditbyamount.",
            parse_mode="HTML",
            disable_web_page_preview=True,
        )
        return
    if len(context.args) == 1 and context.args[0].lower() in ("gpay", "gpay.one", "astropay"):
        context.args = ["gpay.one", GPAY_MERCHANT_ID, GPAY_MERCHANT_PASS]
    if len(context.args) < 3:
        await update.message.reply_text(
            "Usage:\n<code>/addgatewayupi</code> (seed GPay.one)\n"
            "<code>/addgatewayupi gpay KEY SECRET</code>",
            parse_mode="HTML",
        )
        return
    provider = context.args[0].lower()
    key = context.args[1].strip()
    secret = context.args[2].strip()
    data.setdefault("settings", {})["gateway_upi"] = {
        "provider": provider,
        "merchant_id": GPAY_MERCHANT_ID,
        "password": GPAY_MERCHANT_PASS,
        "api_base": GPAY_API_BASE,
        "portal": GPAY_PORTAL,
        "key": key,
        "secret": secret,
        "enabled": True,
        "updated": time.time(),
    }
    save(data)
    await update.message.reply_text(
        f"✅ Gateway saved\nProvider: <b>{provider}</b>\nKey: <code>{key[:12]}…</code>\n"
        f"Portal: {GPAY_PORTAL}\n"
        f"Whitelist server IP + set notify URL in portal.",
        parse_mode="HTML",
    )


async def cmd_setgatewaykey(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Owner: /setgatewaykey YOUR_KEY_ID"""
    data = load()
    if not is_owner(data, update.effective_user.id):
        return
    if not context.args:
        await update.message.reply_text("Usage: /setgatewaykey rzp_live_xxxxx")
        return
    data.setdefault("settings", {}).setdefault("gateway_upi", {})["key"] = context.args[0].strip()
    data["settings"]["gateway_upi"]["enabled"] = True
    save(data)
    await update.message.reply_text("✅ Gateway key updated")


async def cmd_setgatewaysecret(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Owner: /setgatewaysecret YOUR_SECRET"""
    data = load()
    if not is_owner(data, update.effective_user.id):
        return
    if not context.args:
        await update.message.reply_text("Usage: /setgatewaysecret xxxxx")
        return
    data.setdefault("settings", {}).setdefault("gateway_upi", {})["secret"] = context.args[0].strip()
    save(data)
    await update.message.reply_text("✅ Gateway secret updated")


async def cmd_gatewaystatus(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load()
    if not is_owner(data, update.effective_user.id):
        return
    gw = (data.get("settings") or {}).get("gateway_upi") or {}
    if not gw.get("key"):
        await update.message.reply_text("❌ No UPI gateway set.\n/addgatewayupi razorpay KEY SECRET")
        return
    await update.message.reply_text(
        f"🇮🇳 Gateway status\n"
        f"Provider: <b>{gw.get('provider','?')}</b>\n"
        f"Key: <code>{(gw.get('key') or '')[:12]}…</code>\n"
        f"Secret: {'set' if gw.get('secret') else 'missing'}\n"
        f"Enabled: {gw.get('enabled', False)}\n\n"
        f"Auto-credit needs HTTPS webhook → server that calls bot credit API.",
        parse_mode="HTML",
    )


async def cmd_setmindeposit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load()
    if not is_owner(data, update.effective_user.id):
        return
    if not context.args:
        await update.message.reply_text(f"Min deposit: ₹{min_dep_val(data):.0f}\nUsage: /setmindeposit 300")
        return
    try:
        v = float(context.args[0])
        if v < 1:
            raise ValueError()
    except Exception:
        await update.message.reply_text("Example: /setmindeposit 300")
        return
    data.setdefault("settings", {})["min_deposit"] = v
    save(data)
    await update.message.reply_text(f"✅ Min deposit set to ₹{v:.0f}")


def wins_channel_id(data) -> int:
    try:
        v = int((data.get("settings") or {}).get("wins_channel") or WINS_CHANNEL_ID or 0)
        return v
    except Exception:
        return int(WINS_CHANNEL_ID or 0)


def format_win_line(w: dict) -> str:
    """AxomCasino Wins style single line."""
    em = w.get("emoji") or "🎮"
    game = w.get("game") or "Game"
    player = w.get("player") or "Anonymous"
    sym = w.get("sym") or "₹"
    amt = float(w.get("amount") or 0)
    mult = float(w.get("mult") or 0)
    # e.g. 🎲 Dice · Anonymous *****9177 won ₹1,344.24 (1.92x)
    return f"{em} {game} · {player} won {sym}{amt:,.2f} ({mult:.2f}x)"


async def flush_wins_channel(context: ContextTypes.DEFAULT_TYPE):
    """Job: post queued wins to channel (Axom style)."""
    try:
        data = load()
        ch = wins_channel_id(data)
        pending = list(data.get("_pending_wins") or [])
        if not ch or not pending:
            return
        data["_pending_wins"] = []
        save(data)
        for w in pending:
            try:
                await context.bot.send_message(ch, format_win_line(w), disable_web_page_preview=True)
                await asyncio.sleep(0.15)
            except Exception as e:
                logger.warning("wins channel post failed: %s", e)
                # put back failed ones
                data = load()
                data.setdefault("_pending_wins", []).append(w)
                save(data)
                break
    except Exception as e:
        logger.warning("flush_wins_channel: %s", e)


async def cmd_setwinschannel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Owner: /setwinschannel -100xxxx  OR run in the channel as /setwinschannel"""
    data = load()
    if not is_owner(data, update.effective_user.id):
        await update.message.reply_text("👑 Owner only")
        return
    chat = update.effective_chat
    cid = None
    if context.args:
        try:
            cid = int(context.args[0])
        except Exception:
            await update.message.reply_text("Usage: /setwinschannel -100xxxxxxxxxx")
            return
    elif chat and chat.type in ("channel", "supergroup", "group"):
        cid = chat.id
    if not cid:
        await update.message.reply_text(
            "Wins channel set karo:\n"
            "1. Channel banao (jaise HR Casino Wins)\n"
            "2. Is bot ko channel me <b>Admin</b> add karo (Post messages)\n"
            "3. Channel me /setwinschannel bhejo\n"
            "   ya /setwinschannel -100xxxxxxxxxx",
            parse_mode="HTML",
        )
        return
    data.setdefault("settings", {})["wins_channel"] = int(cid)
    save(data)
    # test post
    try:
        await context.bot.send_message(
            int(cid),
            "∞ HR Casino Wins · Logger connected ✅\nWins will appear here live.",
        )
    except Exception as e:
        await update.message.reply_text(
            f"Channel ID saved: <code>{cid}</code>\n"
            f"⚠️ Test post failed: {e}\n"
            f"Bot ko channel me Admin banao (Post messages on).",
            parse_mode="HTML",
        )
        return
    await update.message.reply_text(
        f"✅ Wins logger channel set:\n<code>{cid}</code>\n"
        f"Main bot hi channel me logs post karega (alag logs bot nahi).",
        parse_mode="HTML",
    )


async def cmd_logs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Owner: /logs [main|deposits|games|admin] [lines]
    Shows last N lines from log files (default 30).
    """
    data = load()
    if not is_owner(data, update.effective_user.id):
        await update.message.reply_text("👑 Owner only")
        return
    which = "main"
    n = 30
    args = context.args or []
    if args:
        a0 = args[0].lower()
        if a0 in ("main", "bot", "hrcasino", "all"):
            which = "main" if a0 != "all" else "all"
        elif a0 in ("dep", "deposit", "deposits"):
            which = "deposits"
        elif a0 in ("game", "games"):
            which = "games"
        elif a0 in ("admin", "admins"):
            which = "admin"
        else:
            try:
                n = max(5, min(80, int(a0)))
            except Exception:
                pass
    if len(args) >= 2:
        try:
            n = max(5, min(80, int(args[1])))
        except Exception:
            pass
    mapping = {
        "main": _LOG_DIR / "hrcasino.log",
        "deposits": _LOG_DIR / "deposits.log",
        "games": _LOG_DIR / "games.log",
        "admin": _LOG_DIR / "admin.log",
    }
    files = list(mapping.items()) if which == "all" else [(which, mapping.get(which, mapping["main"]))]
    chunks = []
    for label, path in files:
        if not path.exists():
            chunks.append(f"📄 <b>{label}</b>\n<code>(empty / not created yet)</code>")
            continue
        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
            tail = lines[-n:] if lines else []
            body = "\n".join(tail) if tail else "(empty)"
            if len(body) > 3500:
                body = "…\n" + body[-3500:]
            chunks.append(f"📄 <b>{label}</b> · last {len(tail)}\n<code>{body}</code>")
        except Exception as e:
            chunks.append(f"📄 <b>{label}</b>\n<code>read error: {e}</code>")
    text = "\n\n".join(chunks)
    if len(text) > 4000:
        text = text[:3900] + "\n…"
    await update.message.reply_text(text, parse_mode="HTML")


async def cmd_offgame(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """ /offdice /offbj /offdart ... or /offgame dice """
    data = load()
    uid = update.effective_user.id
    if not is_owner(data, uid) and uid not in set(data.get("bot_admins") or []):
        await update.message.reply_text("👑 Owner / Admin only")
        return
    cmd = (update.message.text or "").split()[0].lower().replace("/", "")
    game = None
    if cmd.startswith("off") and len(cmd) > 3:
        game = cmd[3:]  # offdice -> dice
    if context.args:
        game = context.args[0].lower()
    aliases = {"d": "dice", "predict": "dr", "roulette": "dr", "slots": "slot", "coinflip": "coin"}
    game = aliases.get(game or "", game)
    if not game:
        await update.message.reply_text("Usage: /offdice · /offbj · /offgame limbo")
        return
    off = data.setdefault("settings", {}).setdefault("disabled_games", [])
    if game not in off:
        off.append(game)
    save(data)
    await update.message.reply_text(
        f"🛠 <b>{game.upper()}</b> disabled\n<blockquote>Players will see: under maintenance</blockquote>",
        parse_mode="HTML",
    )


async def cmd_ongame(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load()
    uid = update.effective_user.id
    if not is_owner(data, uid) and uid not in set(data.get("bot_admins") or []):
        await update.message.reply_text("👑 Owner / Admin only")
        return
    cmd = (update.message.text or "").split()[0].lower().replace("/", "")
    game = None
    if cmd.startswith("on") and len(cmd) > 2 and cmd not in ("on", "ongame"):
        game = cmd[2:]
    if context.args:
        game = context.args[0].lower()
    if not game:
        await update.message.reply_text("Usage: /ondice · /onbj · /ongame limbo")
        return
    off = data.setdefault("settings", {}).setdefault("disabled_games", [])
    data["settings"]["disabled_games"] = [x for x in off if str(x).lower() != game]
    save(data)
    await update.message.reply_text(f"✅ <b>{game.upper()}</b> enabled", parse_mode="HTML")


async def cmd_announcement(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load()
    uid = update.effective_user.id
    if not is_owner(data, uid) and uid not in set(data.get("bot_admins") or []):
        await update.message.reply_text("👑 Owner / Admin only")
        return
    msg = update.message
    text_ann = " ".join(context.args or []).strip()
    if msg.reply_to_message and not text_ann:
        text_ann = msg.reply_to_message.text or msg.reply_to_message.caption or ""
    if not text_ann:
        await update.message.reply_text("Usage: /announcement Your message here\nOr reply to a message with /announcement")
        return
    gid = data.get("settings", {}).get("group_id") or GROUP_ID
    body = (
        f"📢 <b>ANNOUNCEMENT</b>\n\n"
        f"<blockquote>{text_ann}</blockquote>"
    )
    try:
        await context.bot.send_message(int(gid), body, parse_mode="HTML")
        await update.message.reply_text("✅ Announcement sent to group.")
    except Exception as e:
        await update.message.reply_text(f"Failed: {e}")


async def cmd_language(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """ /language en | /language hi """
    data = load()
    user = update.effective_user
    ensure_user(data, user)
    args = [a.lower() for a in (context.args or [])]
    if not args or args[0] not in ("en", "english", "hi", "hinglish", "hindi"):
        await update.message.reply_text(t(data, user.id, "lang_usage"))
        return
    lang = "en" if args[0] in ("en", "english") else "hi"
    data["users"][str(user.id)]["lang"] = lang
    save(data)
    await update.message.reply_text(t(data, user.id, "lang_set"))



def make_escrow_card(eid, sender, amount) -> str:
    from PIL import Image, ImageDraw
    W, H = 1200, 620
    img = Image.new("RGB", (W, H), (12, 4, 40))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([20, 20, W-20, H-20], radius=28, outline=(180, 90, 255), width=4)
    d.ellipse([W//2-90, 70, W//2+90, 250], outline=(200, 140, 255), width=6)
    d.rounded_rectangle([W//2-30, 130, W//2+30, 200], radius=8, outline=(220, 180, 255), width=5)
    d.ellipse([W//2-12, 155, W//2+12, 179], outline=(220, 180, 255), width=3)
    d.text((W//2-220, 280), "HR CASINO", fill=(255, 255, 255), font=_pil_font(48, True))
    d.text((W//2-200, 350), "SECURE ESCROW", fill=(200, 160, 255), font=_pil_font(28, True))
    d.text((80, 430), f"#{eid}   Rs {float(amount):.0f}", fill=(250, 204, 21), font=_pil_font(32, True))
    d.text((80, 490), f"From {str(sender)[:18]}", fill=(200, 200, 220), font=_pil_font(22, True))
    out = f"escrow_{eid}.png"
    img.save(out, "PNG")
    return out


async def cmd_payments(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Payment history — sent in DM like private activity."""
    data = load()
    user = update.effective_user
    ensure_user(data, user)
    logs = data.get("paylog", [])
    mine = [p for p in logs if int(p.get("user_id") or 0) == user.id]
    if is_owner(data, user.id) and (context.args and context.args[0].lower() == "all"):
        mine = logs[-30:]
        title = "All payments"
    else:
        mine = mine[-20:]
        title = "Your payment activity"
    if not mine:
        msg = f"{ce('money','💰')} <b>{title}</b>\nNo records yet."
    else:
        lines = [f"{ce('money','💰')} <b>{title}</b>"]
        for p in reversed(mine):
            lines.append(
                f"{p.get('ts','')} · {p.get('kind','')} · ₹{float(p.get('amount',0)):.0f} · {p.get('extra','')}"
            )
        msg = "\n".join(lines)
    try:
        await context.bot.send_message(user.id, msg, parse_mode="HTML")
        if update.effective_chat and update.effective_chat.type != "private":
            await update.message.reply_text("📩 Payment activity DM mein bhej di.")
    except Exception:
        await update.message.reply_text("DM the bot /start first, then /payments")


async def cmd_escrow(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """ /escrow @user amount  — safe P2P hold """
    data = load()
    user = update.effective_user
    u = ensure_user(data, user)
    target = find_target(update, context.args)
    amount = parse_amount(context.args)
    if not target or not amount or amount <= 0:
        await update.message.reply_text(
            "🔒 Escrow (safe deal)\n"
            "Usage:\n"
            "/escrow @user 100\n"
            "or reply + /escrow 100\n\n"
            "Other: /escrowaccept ID · /escrowrelease ID · /escrowcancel ID · /escrowlist"
        )
        return
    if target == user.id:
        await update.message.reply_text("Khud se escrow nahi")
        return
    if float(u.get("balance", 0)) < amount:
        await update.message.reply_text(f"❌ Low balance · ₹{float(u.get('balance',0)):.0f}")
        return
    if not take_bal(data, str(user.id), amount):
        return
    eid = rid("ES")
    data.setdefault("escrows", {})[eid] = {
        "id": eid,
        "from": user.id,
        "to": target,
        "amount": amount,
        "status": "pending",  # pending -> active -> released/cancelled
        "time": time.time(),
    }
    save(data)
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Accept", callback_data=f"esc_acc_{eid}")],
        [
            InlineKeyboardButton("🔓 RLS", callback_data=f"esc_rls_{eid}"),
            InlineKeyboardButton("💸 Refund", callback_data=f"esc_ref_{eid}"),
            InlineKeyboardButton("❌ Cancel", callback_data=f"esc_dec_{eid}"),
        ],
    ])
    cap = (
        f"🔒 SECURE ESCROW #{eid}\n"
        f"From: {user.first_name}\n"
        f"To: {target}\n"
        f"Amount: ₹{amount:.0f} locked\n\n"
        f"🔓 RLS = paise receiver ko\n"
        f"💸 Refund = wapas sender\n"
        f"❌ Cancel"
    )
    try:
        img = make_escrow_card(eid, user.first_name, amount)
        await update.message.reply_photo(photo=open(img, "rb"), caption=cap, reply_markup=kb)
    except Exception as e:
        logger.warning("escrow img %s", e)
        await update.message.reply_text(cap, reply_markup=kb)

    try:
        await context.bot.send_message(
            target,
            f"🔒 Escrow offer\nFrom: {user.first_name}\n₹{amount:.0f}\nID: {eid}\n/escrowaccept {eid}",
        )
    except Exception:
        pass


async def cmd_escrowaccept(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load()
    user = update.effective_user
    if not context.args:
        await update.message.reply_text("Usage: /escrowaccept ES123456")
        return
    eid = context.args[0].strip()
    esc = data.get("escrows", {}).get(eid)
    if not esc or esc.get("status") != "pending":
        await update.message.reply_text("Invalid / already handled")
        return
    if user.id != int(esc["to"]):
        await update.message.reply_text("Ye escrow tumhare liye nahi")
        return
    esc["status"] = "active"
    save(data)
    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("🔓 Release", callback_data=f"esc_rls_{eid}"),
        InlineKeyboardButton("💸 Refund", callback_data=f"esc_ref_{eid}"),
        InlineKeyboardButton("❌ Cancel", callback_data=f"esc_dec_{eid}"),
    ]])
    await update.message.reply_text(
        f"✅ Escrow ACTIVE #{eid}\n₹{esc['amount']:.0f} locked\n\n"
        f"🔓 Release · 💸 Refund · ❌ Cancel",
        reply_markup=kb,
    )


async def cmd_escrowrelease(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load()
    user = update.effective_user
    if not context.args:
        await update.message.reply_text("Usage: /escrowrelease ES123456")
        return
    eid = context.args[0].strip()
    esc = data.get("escrows", {}).get(eid)
    if not esc or esc.get("status") not in ("pending", "active"):
        await update.message.reply_text("Invalid escrow")
        return
    # sender or owner can release
    if user.id != int(esc["from"]) and not is_owner(data, user.id):
        await update.message.reply_text("Sirf sender / owner release kar sakta hai")
        return
    amt = float(esc["amount"])
    add_bal(data, str(esc["to"]), amt)
    esc["status"] = "released"
    save(data)
    await update.message.reply_text(f"✅ Released ₹{amt:.0f} → user {esc['to']}")
    try:
        await context.bot.send_message(int(esc["to"]), f"✅ Escrow #{eid} released · +₹{amt:.0f}")
    except Exception:
        pass


async def cmd_escrowcancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load()
    user = update.effective_user
    if not context.args:
        await update.message.reply_text("Usage: /escrowcancel ES123456")
        return
    eid = context.args[0].strip()
    esc = data.get("escrows", {}).get(eid)
    if not esc or esc.get("status") not in ("pending", "active"):
        await update.message.reply_text("Invalid escrow")
        return
    if user.id not in (int(esc["from"]), int(esc["to"])) and not is_owner(data, user.id):
        await update.message.reply_text("Not allowed")
        return
    # refund to sender
    add_bal(data, str(esc["from"]), float(esc["amount"]))
    esc["status"] = "cancelled"
    save(data)
    await update.message.reply_text(f"❌ Escrow cancelled · ₹{esc['amount']:.0f} wapas sender ko")


async def cmd_escrowlist(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load()
    uid = update.effective_user.id
    lines = ["🔒 Your escrows"]
    for eid, e in list(data.get("escrows", {}).items())[-20:]:
        if uid in (int(e.get("from", 0)), int(e.get("to", 0))) or is_owner(data, uid):
            lines.append(f"#{eid} ₹{e['amount']:.0f} {e['status']} ({e['from']}→{e['to']})")
    if len(lines) == 1:
        lines.append("Koi active escrow nahi")
    await update.message.reply_text("\n".join(lines))




# ----- BLACKJACK -----
def _bj_rank(c):
    s = str(c)
    for ch in "♥♦♣♠":
        s = s.replace(ch, "")
    return s.strip()


def bj_hand_value(cards):
    total, aces = 0, 0
    for c in cards:
        r = _bj_rank(c)
        if r in ("J", "Q", "K"):
            total += 10
        elif r == "A":
            aces += 1
            total += 11
        else:
            try:
                total += int(r)
            except Exception:
                total += 0
    while total > 21 and aces:
        total -= 10
        aces -= 1
    return total


def bj_draw():
    ranks = ["A", "2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K"]
    suits = ["♠", "♥", "♦", "♣"]
    return secrets.choice(ranks) + secrets.choice(suits)


def bj_fmt(cards):
    return " ".join(str(c) for c in cards)


async def cmd_bj(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_group(update, context):
        return
    data = load()
    if not await check_bot_and_game(update, context, data, "bj"):
        return
    user = update.effective_user
    u = ensure_user(data, user)
    stake = parse_amount(context.args) or 0
    mn = float(data["settings"].get("min_bet", MIN_BET))
    if stake < mn:
        await update.message.reply_text(f"Usage: `/bj 20`", parse_mode="Markdown")
        return
    if float(u.get("balance", 0)) < stake:
        await update.message.reply_text(
            t(data, user.id, "low_bal", bal=float(u.get("balance", 0)), need=stake)
        )
        return
    if not take_bal(data, str(user.id), stake):
        await update.message.reply_text("Low balance!")
        return
    player = [bj_draw(), bj_draw()]
    dealer = [bj_draw(), bj_draw()]
    pid = rid("BJ")
    data.setdefault("bj", {})[str(user.id)] = {
        "id": pid,
        "stake": stake,
        "player": player,
        "dealer": dealer,
        "done": False,
        "time": time.time(),
    }
    save(data)
    pv = bj_hand_value(player)
    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("🃏 HIT", callback_data=f"bj_hit_{user.id}"),
        InlineKeyboardButton("🛑 STAND", callback_data=f"bj_stand_{user.id}"),
    ]])
    try:
        img_path = make_bj_card(player, dealer, pv, 0, stake, "HIT or STAND?", f"Bet Rs {stake:.0f}", hide_dealer=True)
        await update.message.reply_photo(
            photo=open(img_path, "rb"),
            caption=f"🃏 BLACKJACK · ₹{stake:.0f}\nHIT or STAND?",
            reply_markup=kb,
        )
    except Exception as e:
        logger.warning("bj start img %s", e)
        await update.message.reply_text(
            f"🃏 BLACKJACK · ₹{stake:.0f}\nDealer: {dealer[0]} ?\nYou: {bj_fmt(player)} ({pv})\nHIT or STAND?",
            reply_markup=kb,
        )



async def bj_finish(q, context, data, user, stand=True):
    uid = str(user.id)
    game = data.get("bj", {}).get(uid)
    if not game or game.get("done"):
        await q.edit_message_text("Game over / not found")
        return
    player = list(game["player"])
    dealer = list(game["dealer"])
    stake = float(game["stake"])
    # dealer plays
    while bj_hand_value(dealer) < 17:
        dealer.append(bj_draw())
    pv, dv = bj_hand_value(player), bj_hand_value(dealer)
    if pv > 21:
        win, payout, msg = False, 0, "BUST — You lose"
    elif dv > 21:
        win, payout, msg = True, round(stake * 2, 2), "Dealer BUST — You win"
    elif pv > dv:
        win, payout, msg = True, round(stake * 2, 2), "YOU WIN"
    elif pv < dv:
        win, payout, msg = False, 0, "DEALER WINS"
    else:
        win, payout, msg = False, stake, "PUSH — stake returned"
        add_bal(data, uid, stake)
        game["done"] = True
        data["bj"].pop(uid, None)
        save(data)
        try:
            img_path = make_bj_card(player, dealer, pv, dv, stake, msg, "PUSH · stake returned", hide_dealer=False)
            try:
                await q.message.delete()
            except Exception:
                pass
            await context.bot.send_photo(
                chat_id=q.message.chat_id,
                photo=open(img_path, "rb"),
                caption=f"🤝 {msg}\n💰 ₹{float(data['users'][uid]['balance']):.0f}",
            )
        except Exception:
            await context.bot.send_message(
                q.message.chat_id,
                f"🃏 BLACKJACK\nDealer: {bj_fmt(dealer)} ({dv})\nYou: {bj_fmt(player)} ({pv})\n🤝 {msg}\n💰 ₹{float(data['users'][uid]['balance']):.0f}",
            )
        return
    if win:
        add_bal(data, uid, payout)
    record(data, user.id, "Blackjack", stake, win and payout > stake, payout if win else 0)
    game["done"] = True
    data["bj"].pop(uid, None)
    save(data)
    result = f"✅ +₹{payout - stake:.0f}" if win and payout > stake else f"❌ -₹{stake:.0f}"
    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton(f"Bet Again {int(stake)}", callback_data=f"bj_again_{int(stake)}"),
        InlineKeyboardButton(f"2x Double {int(stake*2)}", callback_data=f"bj_again_{int(stake*2)}"),
    ]])
    bal = float(data["users"][uid]["balance"])
    result_line = result if "result" in dir() else (f"+Rs {payout-stake:.0f}" if win and payout > stake else f"-Rs {stake:.0f}")
    try:
        img_path = make_bj_card(player, dealer, pv, dv, stake, msg, f"{result_line}  |  Bal Rs {bal:.0f}", hide_dealer=False)
        try:
            await q.message.delete()
        except Exception:
            pass
        await context.bot.send_photo(
            chat_id=q.message.chat_id,
            photo=open(img_path, "rb"),
            caption=f"🃏 {msg}\n💰 Balance: ₹{bal:.0f}",
            reply_markup=kb,
        )
    except Exception as e:
        logger.warning("bj finish img %s", e)
        try:
            await q.message.delete()
        except Exception:
            pass
        await context.bot.send_message(
            q.message.chat_id,
            f"🃏 BLACKJACK · ₹{stake:.0f}\nDealer: {bj_fmt(dealer)} ({dv})\nYou: {bj_fmt(player)} ({pv})\n{msg}\n{result_line}\n💰 ₹{bal:.0f}",
            reply_markup=kb,
        )



async def on_new_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.new_chat_members:
        return
    if not is_target_group(update):
        return
    data = load()
    link = data.get("settings", {}).get("group_link") or GROUP_LINK
    gname = data["settings"].get("group_name", GROUP_NAME)
    for m in update.message.new_chat_members:
        if m.is_bot:
            continue
        ensure_user(data, m)
        save(data)
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🎲 Play /dice 50", callback_data="quick_dice")],
            [InlineKeyboardButton("📖 Help", callback_data="help_show")],
        ])
        caption = (
            f"{ce('gem','💎')} <b>Welcome to {gname}</b> {ce('party','🎉')}\n"
            f"{ce('wave','👋')} <b>{m.first_name}</b>\n"
            f"{ce('fire','🔥')} /dice 50 · /bj 20 · /wallet · /help\n"
            f"{ce('money','💰')} /wallet · /deposit"
        )
        try:
            banner = None
            for p in (Path("nova_welcome.jpg"), Path("/home/container/nova_welcome.jpg"), Path("/home/workdir/artifacts/nova_welcome.jpg")):
                if p.exists():
                    banner = str(p)
                    break
            if banner:
                await update.message.reply_photo(photo=open(banner, "rb"), caption=caption, parse_mode="HTML", reply_markup=kb)
            else:
                b = make_welcome_banner()
                await update.message.reply_photo(photo=open(b, "rb"), caption=caption, parse_mode="HTML", reply_markup=kb)
        except Exception as e:
            logger.warning("welcome member %s", e)
            await update.message.reply_text(caption, parse_mode="HTML", reply_markup=kb)



async def cmd_limbo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """ /limbo 50 2.5 — target multiplier """
    if not await require_group(update, context):
        return
    data = load()
    if not await check_bot_and_game(update, context, data, "limbo"):
        return
    user = update.effective_user
    u = ensure_user(data, user)
    args = context.args or []
    if len(args) < 2:
        await update.message.reply_text(
            "🎯 *Limbo*\n"
            "`/limbo <stake> <target>`\n"
            "Example: `/limbo 50 2.00`\n"
            "Roll ≥ target → win",
            parse_mode="Markdown",
        )
        return
    try:
        stake = float(args[0])
        target = float(args[1])
    except Exception:
        await update.message.reply_text("Invalid numbers. Example: `/limbo 50 2`", parse_mode="Markdown")
        return
    if target < 1.01 or target > 100:
        await update.message.reply_text("Target 1.01 – 100 ke beech rakho")
        return
    mn = min_bet_val(data)
    mx = float(data["settings"].get("max_bet", MAX_BET))
    if stake < mn or stake > mx:
        await update.message.reply_text(f"Stake ₹{mn:.0f} – ₹{mx:.0f}")
        return
    if float(u.get("balance", 0)) < stake:
        await update.message.reply_text(
            f"❌ Low balance!\nBal: ₹{float(u.get('balance', 0)):.0f}"
        )
        return
    if not take_bal(data, str(user.id), stake):
        return
    # Crash distribution: P(roll >= target) is approximately (1 - house fee) / target.
    draw = secrets.randbelow(10**12) / 10**12
    roll = round(min(1000.0, (1 - HOUSE_TAX) / max(1e-12, 1 - draw)), 2)
    win = roll >= target
    mult = target * (1 - HOUSE_TAX)
    payout = round(stake * mult, 2) if win else 0
    if win:
        add_bal(data, str(user.id), payout)
    record(data, user.id, "Limbo", stake, win, payout)
    save(data)
    bal = float(data["users"][str(user.id)]["balance"])
    try:
        img_path = make_limbo_card(stake, target, roll, win, payout, bal)
        caption = (
            f"{'🏆 WIN' if win else '💔 LOSS'} · Limbo\n"
            f"Target {target:.2f}x · Roll {roll:.2f}x\n"
            f"💰 Balance: ₹{bal:.0f}"
        )
        await update.message.reply_photo(photo=open(img_path, "rb"), caption=caption)
    except Exception as e:
        logger.warning("limbo img %s", e)
        await update.message.reply_text(
            f"🎯 LIMBO · {'WIN' if win else 'LOSS'}\n"
            f"Target {target:.2f}x · Roll {roll:.2f}x\n💰 ₹{bal:.0f}"
        )



# ----- MONEY RAIN -----
async def cmd_rain(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """ /rain 100 3 — claim button, first N claimers get share """
    data = load()
    if not is_owner(data, update.effective_user.id):
        await update.message.reply_text("👑 Owner only")
        return
    if not await require_group(update, context):
        return
    if len(context.args) < 2:
        await update.message.reply_text(
            "🌧️ Usage: `/rain 100 3`\n"
            "(total ₹, kitne log claim kar sake)\n"
            "Button tap → balance add",
            parse_mode="Markdown",
        )
        return
    try:
        total = float(context.args[0])
        slots = int(context.args[1])
    except Exception:
        await update.message.reply_text("Invalid numbers")
        return
    if slots < 1 or slots > 50 or total < slots:
        await update.message.reply_text("Slots 1-50, total ≥ slots")
        return
    owner = update.effective_user
    ou = ensure_user(data, owner)
    if float(ou.get("balance", 0)) < total:
        await update.message.reply_text("❌ Owner balance too low")
        return
    if not take_bal(data, str(owner.id), total):
        return
    rid_rain = rid("RN")
    each = round(total / slots, 2)
    data.setdefault("rains", {})[rid_rain] = {
        "id": rid_rain,
        "total": total,
        "slots": slots,
        "each": each,
        "claimed": [],  # user ids
        "owner": owner.id,
        "chat_id": update.effective_chat.id,
        "active": True,
        "time": time.time(),
    }
    save(data)
    left = slots
    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton(f"🌧️ Claim ₹{each:.0f} ({left}/{slots})", callback_data=f"rain_{rid_rain}")
    ]])
    await update.message.reply_text(
        f"🌧️ *MONEY RAIN*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"💰 Total: *₹{total:.0f}*\n"
        f"👥 Slots: *{slots}* · Each ~₹{each:.0f}\n\n"
        f"✅ Claim conditions:\n"
        f"• Name must include `@HRCasino`\n"
        f"• Complete at least *10 games*\n"
        f"━━━━━━━━━━━━━━━━━━━━",
        parse_mode="Markdown",
        reply_markup=kb,
    )



async def cmd_addbotadmin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load()
    if not is_owner(data, update.effective_user.id):
        return
    if not context.args:
        await update.message.reply_text("Usage: /addbotadmin USER_ID")
        return
    aid = str(context.args[0])
    data.setdefault("bot_admins", [])
    if aid not in data["bot_admins"]:
        data["bot_admins"].append(aid)
    save(data)
    await update.message.reply_text(
        f"✅ Bot admin: `{aid}`\nThey can use /setbrand Name",
        parse_mode="Markdown",
    )


async def cmd_removebotadmin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load()
    if not is_owner(data, update.effective_user.id) or not context.args:
        return
    aid = str(context.args[0])
    data["bot_admins"] = [x for x in data.get("bot_admins", []) if x != aid]
    save(data)
    await update.message.reply_text("Removed")


async def cmd_setbrand(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load()
    uid = str(update.effective_user.id)
    if not is_owner(data, update.effective_user.id) and uid not in data.get("bot_admins", []):
        await update.message.reply_text("Owner/Bot-admin only")
        return
    if not context.args:
        await update.message.reply_text("Usage: /setbrand HR Casino")
        return
    name = " ".join(context.args)
    data.setdefault("settings", {})["group_name"] = name
    save(data)
    await update.message.reply_text(f"✅ Brand name: *{name}*", parse_mode="Markdown")



async def cmd_makecode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Owner: /makecode CODE amount uses"""
    data = load()
    if not is_owner(data, update.effective_user.id):
        return
    args = context.args or []
    nl = chr(10)
    if len(args) < 2:
        await reply_prem(update.message, [
            ("promo",), " Create promo", nl, nl,
            "/makecode WELCOME50 50 20", nl,
            "code · amount · max uses (optional)",
        ])
        return
    code = args[0].upper().strip()
    try:
        amount = float(args[1])
    except Exception:
        await reply_prem(update.message, [("error",), " Invalid amount"])
        return
    uses = int(args[2]) if len(args) > 2 else 100
    data.setdefault("promos", {})[code] = {
        "amount": amount,
        "uses_left": uses,
        "redeemed": [],
    }
    save(data)
    await reply_prem(update.message, [
        ("check",), " Promo created", nl,
        f"Code: {code}", nl,
        f"Amount: ₹{amount:.0f}", nl,
        f"Uses: {uses}",
    ])


async def cmd_promo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """User: /promo CODE"""
    data = load()
    user = update.effective_user
    u = ensure_user(data, user)
    args = context.args or []
    nl = chr(10)
    if not args:
        await reply_prem(update.message, [
            ("promo",), " Redeem promo", nl, nl,
            "/promo YOURCODE",
        ])
        return
    code = args[0].upper().strip()
    promo = (data.get("promos") or {}).get(code)
    if not promo:
        await reply_prem(update.message, [("error",), " Invalid or expired code"])
        return
    uid = str(user.id)
    if uid in promo.get("redeemed", []):
        await reply_prem(update.message, [("warn",), " You already redeemed this code"])
        return
    if int(promo.get("uses_left", 0)) <= 0:
        await reply_prem(update.message, [("error",), " Code fully used"])
        return
    amount = float(promo["amount"])
    add_bal(data, uid, amount)
    promo["uses_left"] = int(promo["uses_left"]) - 1
    promo.setdefault("redeemed", []).append(uid)
    save(data)
    await reply_prem(update.message, [
        ("party",), " Promo redeemed!", nl,
        ("money",), f" +₹{amount:.0f}", nl,
        ("money",), f" Balance: ₹{float(data['users'][uid]['balance']):.0f}",
    ])


def resolve_user_id(data, token: str, bot_users_hint=None):
    """Resolve @username or numeric id from known users."""
    token = (token or "").strip().lstrip("@")
    if token.isdigit():
        return int(token)
    tl = token.lower()
    for uid, u in (data.get("users") or {}).items():
        if (u.get("username") or "").lower() == tl:
            return int(uid)
    return None


async def cmd_tip(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load()
    user = update.effective_user
    u = ensure_user(data, user)
    target_id = find_target(update, context.args)
    stake = parse_amount(context.args)
    nl = chr(10)
    if not target_id or not stake or stake <= 0:
        parts = [
            ("gift",), " Tip", nl, nl,
            "Usage:", nl,
            "/tip @username 10", nl,
            "/tip 123456789 10", nl,
            "or reply to a message with /tip 10",
        ]
        await reply_prem(update.message, parts)
        return
    if target_id == user.id:
        await reply_prem(update.message, [("error",), " You cannot tip yourself"])
        return
    if float(u.get("balance", 0) or 0) < stake:
        await reply_prem(update.message, [
            ("error",), " Low balance", nl,
            ("money",), " ₹{:.0f}".format(float(u.get("balance", 0) or 0)),
        ])
        return
    if str(target_id) not in data.get("users", {}):
        data.setdefault("users", {})[str(target_id)] = {
            "balance": 0.0, "ref_code": rid("R"), "referred_by": None,
            "referrals": 0, "wagered": 0.0, "won": 0.0, "lost": 0.0,
            "bets": 0, "username": "", "name": str(target_id), "joined": str(date.today()),
        }
    # Confirm before sending tip
    from_tag = ("@" + user.username) if user.username else (user.first_name or "Someone")
    to_u = data["users"].get(str(target_id), {})
    to_tag = ("@" + to_u.get("username", "")) if to_u.get("username") else str(target_id)
    data.setdefault("pending_tips", {})[str(user.id)] = {
        "to": str(target_id), "amount": float(stake), "time": time.time(),
    }
    save(data)
    kb = InlineKeyboardMarkup([[
        style_btn("✅ Confirm", style="success", callback_data=f"tipok_{user.id}_{target_id}_{int(stake)}"),
        style_btn("❌ Decline", style="danger", callback_data=f"tipno_{user.id}"),
    ]])
    await reply_prem(update.message, [
        ("gift",), " Confirm Tip", nl, nl,
        "To » ", to_tag, nl,
        "Amount » ₹{:.0f}".format(stake), nl, nl,
        "Confirm or Decline:",
    ], reply_markup=kb)
    return
    # legacy unreachable
    if not take_bal(data, str(user.id), stake):
        await reply_prem(update.message, [("error",), " Low balance"])
        return
    add_bal(data, str(target_id), stake)
    save(data)
    from_tag = ("@" + user.username) if user.username else (user.first_name or "Someone")
    to_u = data["users"].get(str(target_id), {})
    to_tag = ("@" + to_u["username"]) if to_u.get("username") else str(target_id)
    await reply_prem(update.message, [
        ("trophy",), " Tip Sent!", nl, nl,
        "From » ", from_tag, nl,
        "To » ", to_tag, nl,
        "Amount » ₹{:.0f}".format(stake),
    ])
    # receiver (BV You received a tip)
    try:
        await context.bot.send_message(
            target_id,
            text=None,
        )
    except Exception:
        pass
    try:
        # build via entities for receiver
        rparts = [
            ("trophy",), " You received a tip!", nl, nl,
            ("user",), " From: ", from_tag, nl,
            ("money",), " Amount: ₹{:.0f} added to your wallet!".format(stake), nl,
            ("bank",), " New Balance: ₹{:.2f}".format(float(data["users"][str(target_id)]["balance"])), nl, nl,
            "Use /wallet to view your balance.",
        ]
        # send using bot API with entities
        txt, ents = build_prem(rparts)
        await context.bot.send_message(target_id, txt, entities=ents)
    except Exception:
        try:
            await context.bot.send_message(
                target_id,
                "You received a tip! +₹{:.0f} from {}\nNew Balance: ₹{:.2f}".format(
                    stake, from_tag, float(data["users"][str(target_id)]["balance"])
                ).replace("\\n", "\n"),
            )
        except Exception:
            pass



# ---------- CALLBACKS ----------

async def ask_mode_from_cb(q, context, data, user, game_key, stake, rule, rounds=1):
    emoji, label = GAMES.get(game_key, ("🎲", game_key))
    kb = InlineKeyboardMarkup([[
        style_btn(f"🤖 Vs Bot", style="primary", callback_data=f"mode_bot_{rule}_{game_key}_{int(stake)}_{user.id}_{int(rounds or 1)}"),
        style_btn("⚔ Open PvP", style="success", callback_data=f"mode_pvp_{rule}_{game_key}_{int(stake)}_{user.id}_{int(rounds or 1)}"),
    ]])
    un = user.username or user.first_name or "Player"
    msg = (
        f"<b>{un}</b>\n"
        f"<code>/{game_key} {int(stake)}</code>\n"
        f"{emoji} <b>{label}</b> ₹{int(stake)}\n\n"
        f"🤖 Play with Bot — play against the bot\n"
        f"✅ Accept Challenge — let another player join (PvP)"
    )
    try:
        await q.edit_message_text(msg, parse_mode="HTML", reply_markup=kb)
    except Exception:
        await q.message.reply_text(msg, parse_mode="HTML", reply_markup=kb)



async def cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    try:
        await q.answer()
    except Exception:
        pass
    data = load()
    user = q.from_user
    d = (q.data or "")
    try:
        ensure_user(data, user)
    except Exception:
        pass
    try:
        await _cb_body(update, context, q, data, user, d)
    except Exception as e:
        logger.exception("callback %s", e)
        try:
            await q.answer("Error — try command again", show_alert=True)
        except Exception:
            pass


async def _cb_body(update, context, q, data, user, d):
    # ----- DiceGamble-style dice callbacks -----
    if d == "dg_cancel":
        data.get("dice_setup", {}).pop(str(user.id), None)
        data.get("dice_open", {}).pop(str(user.id), None)
        save(data)
        try:
            await q.edit_message_text("❌ Cancelled.")
        except Exception:
            pass
        return
    if d == "dg_guide":
        await q.message.reply_text(
            "🎲 <b>Mode Guide</b>\n"
            "<blockquote>"
            "<b>Normal</b> — 1 die, higher wins point, first to 2\n"
            "<b>Double</b> — 2 dice sum, higher wins point\n"
            "<b>Triple</b> — 3 dice sum, higher wins point\n"
            "<b>Crazy</b> — lower score wins the point\n"
            "<b>Crazy Double/Triple</b> — crazy + multi dice\n"
            f"Win multiplier: <b>{DICE_WIN_MULT}×</b>\n"
            "</blockquote>",
            parse_mode="HTML",
        )
        return
    if d.startswith("dg_mode_"):
        mode = d.replace("dg_mode_", "", 1)
        setup = (data.get("dice_setup") or {}).get(str(user.id))
        if not setup:
            await q.answer("Session expired — send /dice again", show_alert=True)
            return
        meta = _dice_mode_meta(mode)
        stake = float(setup["stake"])
        setup["mode"] = mode
        data["dice_setup"][str(user.id)] = setup
        save(data)
        B = InlineKeyboardButton
        kb = InlineKeyboardMarkup([[
            B("✅ Confirm", callback_data="dg_confirm"),
            B("❌ Cancel", callback_data="dg_cancel"),
        ]])
        try:
            await q.edit_message_text(
                f"<blockquote>🎲 {user.first_name}\n/dice {stake:.0f}</blockquote>\n"
                f"🎲 <b>Game confirmation</b>\n\n"
                f"Game: Dice 🎲\n"
                f"First to {meta['pts']} points\n"
                f"Mode: <b>{meta['label']}</b>\n"
                f"Your bet: <b>₹{stake:.2f}</b> 🔥\n"
                f"Win multiplier: <b>{DICE_WIN_MULT}×</b>",
                parse_mode="HTML",
                reply_markup=kb,
            )
        except Exception:
            await q.message.reply_text("Confirm bet:", reply_markup=kb)
        return
    if d == "dg_confirm":
        setup = (data.get("dice_setup") or {}).get(str(user.id))
        if not setup:
            await q.answer("Session expired — /dice again", show_alert=True)
            return
        stake = float(setup["stake"])
        mode = setup.get("mode") or "normal"
        meta = _dice_mode_meta(mode)
        u = ensure_user(data, user)
        if float(u.get("balance", 0) or 0) < stake:
            await q.answer("Low balance", show_alert=True)
            return
        if not take_bal(data, str(user.id), stake):
            await q.answer("Balance error", show_alert=True)
            return
        # open public match offer
        oid = str(user.id)
        data.setdefault("dice_open", {})[oid] = {
            "stake": stake,
            "mode": mode,
            "player1": user.id,
            "name1": user.first_name or "P1",
            "time": time.time(),
            "chat_id": q.message.chat_id,
        }
        data.get("dice_setup", {}).pop(oid, None)
        save(data)
        B = InlineKeyboardButton
        kb = InlineKeyboardMarkup([
            [
                B("✅ Accept Match", callback_data=f"dg_accept_{user.id}"),
                B("✅ Play against bot", callback_data=f"dg_bot_{user.id}"),
            ],
            [B("❌ Cancel", callback_data=f"dg_cancel_open_{user.id}")],
        ])
        try:
            await q.edit_message_text(
                f"<blockquote>🎲 {user.first_name}\n/dice {stake:.0f}</blockquote>\n"
                f"🎲 <b>{user.first_name} wants to play Dice!</b>\n\n"
                f"Bet: <b>₹{stake:.2f}</b> 🔥\n"
                f"Win multiplier: <b>{DICE_WIN_MULT}×</b>\n"
                f"Mode: <b>First to {meta['pts']} points</b>\n\n"
                f"<b>{meta['label']}</b>\n"
                f"{meta['desc']}\n\n"
                f"If you want to play, click <b>Accept Match</b>",
                parse_mode="HTML",
                reply_markup=kb,
            )
        except Exception:
            await q.message.reply_text("Match open — Accept / vs Bot", reply_markup=kb)
        return
    if d.startswith("dg_cancel_open_"):
        oid = d.split("_")[-1]
        if str(user.id) != oid and not is_owner(data, user.id):
            await q.answer("Only match owner can cancel", show_alert=True)
            return
        openm = (data.get("dice_open") or {}).pop(oid, None)
        if openm:
            add_bal(data, oid, float(openm.get("stake") or 0))
            save(data)
        try:
            await q.edit_message_text("❌ Match cancelled — bet refunded.")
        except Exception:
            pass
        return
    if d.startswith("dg_accept_") or d.startswith("dg_bot_"):
        vs_bot = d.startswith("dg_bot_")
        oid = d.split("_")[-1]
        openm = (data.get("dice_open") or {}).get(oid)
        if not openm:
            await q.answer("Match expired", show_alert=True)
            return
        if not vs_bot and str(user.id) == oid:
            await q.answer("You cannot accept your own match", show_alert=True)
            return
        stake = float(openm["stake"])
        mode = openm.get("mode") or "normal"
        meta = _dice_mode_meta(mode)
        if not vs_bot:
            u2 = ensure_user(data, user)
            if float(u2.get("balance", 0) or 0) < stake:
                await q.answer("Low balance to accept", show_alert=True)
                return
            if not take_bal(data, str(user.id), stake):
                return
            p2_id, p2_name = user.id, (user.first_name or "P2")
        else:
            if str(user.id) != oid:
                await q.answer("Only creator can play vs bot", show_alert=True)
                return
            p2_id, p2_name = 0, "Bot"
        data.get("dice_open", {}).pop(oid, None)
        mid = f"dg{int(time.time())%100000}{oid[-4:]}"
        data.setdefault("dice_live", {})[mid] = {
            "stake": stake,
            "mode": mode,
            "p1": int(oid),
            "p2": int(p2_id),
            "n1": openm.get("name1") or "P1",
            "n2": p2_name,
            "s1": 0,
            "s2": 0,
            "pts": meta["pts"],
            "rolls": meta["rolls"],
            "crazy": meta["crazy"],
            "turn": int(oid),  # p1 starts
            "turn_rolls": [],
            "chat_id": q.message.chat_id,
            "vs_bot": vs_bot,
        }
        save(data)
        try:
            await q.edit_message_text(
                f"🎲 <b>Match accepted!</b>\n\n"
                f"Player 1: <b>{openm.get('name1')}</b>\n"
                f"Player 2: <b>{p2_name}</b>\n\n"
                f"<b>{openm.get('name1')}</b>, your turn! To start, send this emoji: 🎲",
                parse_mode="HTML",
            )
        except Exception:
            pass
        # if vs bot, after p1 rolls bot will auto - handled in dice handler
        return
    if d.startswith("dg_again_") or d.startswith("dg_double_"):
        # Play again / double — reopen setup with same or 2x stake
        parts = d.split("_")
        stake = float(parts[-1]) if parts[-1].replace(".", "").isdigit() else min_bet_val(data)
        if d.startswith("dg_double_"):
            stake = stake * 2
        u = ensure_user(data, user)
        if float(u.get("balance", 0) or 0) < stake:
            await q.answer("Low balance", show_alert=True)
            return
        data.setdefault("dice_setup", {})[str(user.id)] = {
            "stake": stake, "time": time.time(), "chat_id": q.message.chat_id,
        }
        save(data)
        B = InlineKeyboardButton
        kb = InlineKeyboardMarkup([
            [B("Normal Mode", callback_data="dg_mode_normal")],
            [B("Double Roll", callback_data="dg_mode_double")],
            [B("Triple Roll (NEW!)", callback_data="dg_mode_triple")],
            [B("Crazy Mode", callback_data="dg_mode_crazy")],
            [B("Crazy Double Roll", callback_data="dg_mode_crazy_double")],
            [B("Crazy Triple Roll (NEW!)", callback_data="dg_mode_crazy_triple")],
            [B("❌ Cancel", callback_data="dg_cancel")],
        ])
        await q.message.reply_text(
            f"🎲 <b>Choose the game mode</b>\nBet: ₹{stake:.2f}",
            parse_mode="HTML",
            reply_markup=kb,
        )
        return

    if d.startswith("setcur_"):
        cur = d.split("_", 1)[1].upper()
        if cur in CURRENCIES:
            ensure_user(data, user)
            data["users"][str(user.id)]["currency"] = cur
            save(data)
            await q.answer(f"Currency: {cur}", show_alert=True)
            try:
                await q.edit_message_text(f"✅ Display currency set to <b>{cur}</b>", parse_mode="HTML")
            except Exception:
                pass
        return
    if d.startswith("setlim_"):
        if not is_owner(data, user.id):
            await q.answer("Owner only", show_alert=True)
            return
        parts = d.split("_")
        # setlim_minbet_50
        if len(parts) >= 3:
            kind, val = parts[1], parts[2]
            try:
                num = float(val)
            except Exception:
                return
            key = {"minbet": "min_bet", "maxbet": "max_bet", "minwd": "min_withdraw", "maxwd": "max_withdraw"}.get(kind)
            if key:
                data["settings"][key] = num
                save(data)
                await q.answer(f"{key}={num}", show_alert=True)
        return
    if d.startswith("setrig_"):
        if not is_owner(data, user.id):
            await q.answer("Owner only", show_alert=True)
            return
        mode = d.split("_", 1)[1]
        if mode in ("off", "active", "full"):
            data["settings"]["rig_mode"] = mode
            save(data)
            await q.answer(f"Rig {mode}", show_alert=True)
        return

    # Deposit methods (UPI / Binance / Crypto addresses)
    if d == "dep_method_upi":
        await q.answer()
        await start_upi_deposit(update, context, user)
        return
    if d in ("dep_method_cc", "dep_method_cctip"):
        await q.answer()
        await start_cc_deposit(update, context, user)
        return
    if d == "dep_method_binance":
        await q.answer("Binance removed. Use UPI / CWallet / Crypto.", show_alert=True)
        return
    if d == "dep_method_cwallet":
        await q.answer()
        data = load()
        uid = str(user.id)
        data.setdefault("pending_dep_step", {})[uid] = {
            "step": "amount", "method": "cwallet", "created": time.time(),
        }
        save(data)
        await q.message.reply_text(
            "💛 <b>CWallet Deposit</b>\n\n"
            "1) Send amount (number) here\n"
            "2) Pay via <b>CWallet</b> / linked bot\n"
            "3) Send screenshot — admin credits\n\n"
            f"Support: @{SUPPORT_PAY}",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("⬅️ Back", callback_data="dep_method_back")],
            ]),
        )
        return
    if d == "wd_method_upi":
        await q.answer()
        data = load()
        data.setdefault("pending_wd_step", {})[str(user.id)] = {"step": "upi", "method": "upi"}
        save(data)
        await q.message.reply_text("🇮🇳 Send your <b>UPI ID</b>:", parse_mode="HTML")
        return
    if d == "wd_method_cwallet":
        await q.answer()
        data = load()
        data.setdefault("pending_wd_step", {})[str(user.id)] = {"step": "detail", "method": "cwallet"}
        save(data)
        await q.message.reply_text(
            "💛 <b>CWallet Withdraw</b>\n\n"
            "Send your CWallet username / ID:",
            parse_mode="HTML",
        )
        return
    if d == "wd_method_cctip":
        await q.answer()
        data = load()
        data.setdefault("pending_wd_step", {})[str(user.id)] = {"step": "detail", "method": "cctip"}
        save(data)
        await q.message.reply_text(
            "🤖 <b>@cctip_bot Withdraw</b>\n\n"
            "Send your Telegram @username for cctip payout:",
            parse_mode="HTML",
        )
        return
    if d == "wd_method_crypto":
        await q.answer()
        data = load()
        data.setdefault("pending_wd_step", {})[str(user.id)] = {"step": "detail", "method": "crypto"}
        save(data)
        await q.message.reply_text(
            "💎 Send network + address\n"
            "Example:\n<code>USDT_TRC20 TNxxxx...</code>",
            parse_mode="HTML",
        )
        return
    if d == "dep_method_back":
        await q.answer()
        try:
            await cmd_deposit(update, context)
        except Exception:
            pass
        return
    if d.startswith("dep_crypto_"):
        await q.answer()
        key = d.replace("dep_crypto_", "", 1)
        if key == "more":
            lines = ["💎 <b>All crypto addresses</b>\n"]
            for k, addr in CRYPTO_WALLETS.items():
                lines.append(f"<b>{k}</b>\n<code>{addr}</code>\n")
            lines.append("\nSend crypto then screenshot in DM with amount.\nSupport: @" + SUPPORT_PAY)
            await q.message.reply_text("\n".join(lines), parse_mode="HTML")
            return
        addr = CRYPTO_WALLETS.get(key) or CRYPTO_WALLETS.get(key.upper())
        if not addr:
            await q.message.reply_text("Unknown network.")
            return
        data = load()
        uid = str(user.id)
        memo = CRYPTO_MEMOS.get(key) or CRYPTO_MEMOS.get(key.upper()) or ""
        data.setdefault("pending_dep_step", {})[uid] = {
            "step": "ss",
            "method": "crypto",
            "network": key,
            "address": addr,
            "memo": memo,
            "created": time.time(),
        }
        save(data)
        memo_line = f"\n⚠️ Memo / tag: <code>{memo}</code> (must include)" if memo else ""
        await q.message.reply_text(
            f"💎 <b>{key}</b> Deposit\n\n"
            f"Send only to:\n<code>{addr}</code>{memo_line}\n\n"
            f"1) Send coin on <b>{key}</b>\n"
            f"2) Tap Payment Done / send screenshot\n"
            f"3) Admin credits after confirm\n\n"
            f"Support: @{SUPPORT_PAY}",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ Payment Done", callback_data="pay_done")],
                [InlineKeyboardButton("🔙 Back", callback_data="dep_method_back")],
            ]),
        )
        return
    if d == "binance_check":
        data = load()
        uid = str(user.id)
        pend = (data.get("pending_binance") or {}).get(uid)
        if not pend:
            await q.message.reply_text("No pending Binance deposit. Use /deposit again.")
            return
        if not BINANCE_API_SECRET:
            await q.message.reply_text(
                "⚠️ Auto-check needs BINANCE_API_SECRET in environment.\n"
                "Admin: set secret + enable deposit history.\n"
                "Or set address with /setbinanceaddr and verify manually."
            )
            return
        deposits = await binance_recent_deposits()
        found = None
        for dep in deposits or []:
            if dep.get("status") in (1, "1", True):
                found = dep
                break
        if not found:
            await q.message.reply_text("⏳ Not confirmed yet. Wait and tap again.")
            return
        if pend.get("status") == "credited":
            await q.message.reply_text("Already credited.")
            return
        try:
            amt = float(found.get("amount") or 0)
        except Exception:
            amt = 0
        if amt <= 0:
            await q.message.reply_text("Invalid deposit amount.")
            return
        rate = float(data.get("settings", {}).get("usdt_inr_rate", 1) or 1)
        credit = round(amt * rate, 2)
        ensure_user(data, user)
        add_bal(data, uid, credit)
        data.setdefault("pending_binance", {})[uid]["status"] = "credited"
        data["pending_binance"][uid]["amount"] = credit
        save(data)
        await q.message.reply_text(
            f"✅ Binance deposit credited +₹{credit:.2f} (USDT {amt})"
        )
        return

    if d == "menu_setwallet":
        await q.message.reply_text("💳 Set payout UPI:\nSend /setwallet yourupi@okaxis")
        return
    if d == "menu_currency":
        await q.message.reply_text("💱 Display currency: INR (default). USD display coming soon.")
        return
    if d == "menu_lang":
        await q.message.reply_text("🌐 /language en  or  /language hi")
        return

    if d.startswith("menu_"):
        uid = str(user.id)
        player = data.get("users", {}).get(uid) or ensure_user(data, user)
        home_kb = private_menu_markup(data)
        B = InlineKeyboardButton
        bal = float(player.get("balance", 0) or 0)

        if d == "menu_home":
            me = await context.bot.get_me()
            name = user.first_name or "Player"
            uname = ("@" + user.username) if user.username else name
            try:
                money = fmt_money(data, user.id, bal)
            except Exception:
                money = f"₹{bal:.2f}"
            gname = (data.get("settings") or {}).get("group_name", GROUP_NAME) or "HR CASINO"
            text = (
                f"⭐ <b>{gname}</b>\n"
                f"<blockquote><b>WELCOME</b>\n"
                f"👤 <b>{name}</b> · {uname}\n"
                f"💰 Balance: <b>{money}</b></blockquote>\n"
                f"👇 Use the menu"
            )
            await _menu_edit(q, text, rolex_main_kb(getattr(me, "username", None)))
            return

        if d == "menu_wallet":
            kb = InlineKeyboardMarkup([
                [B("💰 Deposit", callback_data="menu_deposit"), B("🚀 Withdraw", callback_data="menu_withdraw")],
                [B("⬅️ Main menu", callback_data="menu_home")],
            ])
            await _menu_edit(
                q,
                f"💰 <b>YOUR WALLET</b>\n<blockquote>"
                f"Balance: <b>₹{bal:.2f}</b>\n"
                f"Min withdraw: ₹{MIN_WITHDRAW}</blockquote>",
                kb,
            )
            return

        if d == "menu_stats":
            await _menu_edit(
                q,
                f"📊 <b>YOUR STATS</b>\n<blockquote>"
                f"Games: {int(player.get('bets', 0) or 0)}\n"
                f"Wagered: ₹{float(player.get('wagered', 0) or 0):.2f}\n"
                f"Won: ₹{float(player.get('won', 0) or 0):.2f}\n"
                f"Lost: ₹{float(player.get('lost', 0) or 0):.2f}\n"
                f"Referrals: {int(player.get('referrals', 0) or 0)}"
                f"</blockquote>",
                home_kb,
            )
            return

        if d == "menu_history":
            history = [b for b in data.get("bets", []) if str(b.get("uid")) == uid][-8:]
            lines = ["🧾 <b>RECENT BETS</b>\n<blockquote>"]
            if not history:
                lines.append("No bets yet.")
            else:
                for bet in reversed(history):
                    result = "WIN" if bet.get("win") else "LOSS"
                    try:
                        when = datetime.fromtimestamp(float(bet.get("time", 0))).strftime("%d %b %H:%M")
                    except Exception:
                        when = "-"
                    lines.append(
                        f"{result} · {bet.get('game', '?')} · ₹{float(bet.get('stake', 0) or 0):.0f} · {when}"
                    )
            lines.append("</blockquote>")
            await _menu_edit(q, "\n".join(lines), home_kb)
            return

        if d == "menu_games":
            kb = InlineKeyboardMarkup([
                [B("🎲 /dice", callback_data="quick_dice"), B("🃏 /bj", callback_data="quick_bj")],
                [B("⬅️ Main menu", callback_data="menu_home")],
            ])
            await _menu_edit(
                q,
                "🎲 <b>GAME ARENA</b>\n<blockquote>"
                "In group use:\n"
                "/dice 50 · /dice all\n"
                "/dart 50 · /bowl 50 · /basket 50\n"
                "/slot 50 · /bj 20 · /limbo 50 2\n"
                "/coin 50 · /mines 50 · /dr high 50\n"
                "/predict 50 1 3 5"
                "</blockquote>",
                kb,
            )
            return

        if d == "menu_jackpot":
            jp = float((data.get("settings") or {}).get("jackpot", 0) or data.get("jackpot", 0) or 0)
            await _menu_edit(
                q,
                f"🎉 <b>JACKPOT</b>\n<blockquote>Pool: <b>₹{jp:.2f}</b>\nUse /jackpot in group</blockquote>",
                home_kb,
            )
            return

        if d == "menu_rules":
            await _menu_edit(
                q,
                "📜 <b>RULES</b>\n<blockquote>"
                "• Play fair — outcomes from Telegram dice\n"
                "• Min bet / deposit as set by admin\n"
                "• Deposit & withdraw in DM only\n"
                "• Games mainly in the game group\n"
                "• House fee may apply on wins\n"
                "• Admin decisions final on disputes"
                "</blockquote>",
                home_kb,
            )
            return

        if d == "menu_help":
            await _menu_edit(
                q,
                "📖 <b>QUICK HELP</b>\n<blockquote>"
                "/wallet · /deposit · /withdraw\n"
                "/dice 50 · /dice all\n"
                "/mystats · /invite · /jackpot\n"
                "/help — full command list\n"
                f"Support: @{SUPPORT_PAY}"
                "</blockquote>",
                home_kb,
            )
            return

        if d == "menu_deposit":
            if q.message.chat.type != "private":
                me = await context.bot.get_me()
                await q.message.reply_text(
                    "⬇️ Deposit in DM:",
                    reply_markup=InlineKeyboardMarkup([[
                        B("💰 Open Deposit", url=f"https://t.me/{me.username}?start=deposit")
                    ]]),
                )
                return
            await cmd_deposit(update, context)
            return

        if d == "menu_withdraw":
            if q.message.chat.type != "private":
                me = await context.bot.get_me()
                await q.message.reply_text(
                    "⬆️ Withdraw in DM:",
                    reply_markup=InlineKeyboardMarkup([[
                        B("🚀 Open Withdraw", url=f"https://t.me/{me.username}?start=withdraw")
                    ]]),
                )
                return
            if bal < MIN_WITHDRAW:
                await q.answer(f"Min withdrawal ₹{MIN_WITHDRAW}", show_alert=True)
                return
            await cmd_withdraw(update, context)
            return

        if d == "menu_group":
            await q.answer("Group invite not set. Owner: /setgrouplink", show_alert=True)
            return

        if d == "menu_setwallet":
            await q.message.reply_text("💳 Set payout UPI:\n<code>/setwallet yourupi@okaxis</code>", parse_mode="HTML")
            return

        if d == "menu_currency":
            await cmd_currency(update, context)
            return

        if d == "menu_lang":
            await q.message.reply_text("🌐 Language:\n/language en\n/language hi")
            return

        await q.answer("Unknown menu", show_alert=True)
        return

    if d.startswith("panel_"):
        if not is_owner(data, user.id):
            await q.answer("Owner only.", show_alert=True)
            return
        if d in ("panel_pause", "panel_resume"):
            data.setdefault("settings", {})["bot_on"] = d == "panel_resume"
            save(data)
            await q.answer("Bot paused." if d == "panel_pause" else "Bot resumed.")
            await edit_prem(q.message, panel_overview_parts(data), reply_markup=panel_keyboard(data))
            return
        if d.startswith("panel_game_toggle_"):
            game = d.removeprefix("panel_game_toggle_")
            if game not in ADMIN_GAMES:
                await q.answer("Unknown game.", show_alert=True)
                return
            disabled = data.setdefault("settings", {}).setdefault("disabled_games", [])
            if game in disabled:
                data["settings"]["disabled_games"] = [g for g in disabled if g != game]
            else:
                disabled.append(game)
            save(data)
            d = "panel_games"
        if d == "panel_close":
            await q.answer()
            await q.edit_message_text("Admin panel closed.")
            return
        if d in ("panel_home", "panel_pause", "panel_resume"):
            await q.answer()
            await edit_prem(q.message, panel_overview_parts(data), reply_markup=panel_keyboard(data))
            return
        if d == "panel_games":
            disabled = set(data.get("settings", {}).get("disabled_games") or [])
            rows = []
            for key, (icon, label) in ADMIN_GAMES.items():
                state = "OFF" if key in disabled else "ON"
                rows.append([InlineKeyboardButton(
                    f"{icon} {label}: {state}",
                    callback_data=f"panel_game_toggle_{key}",
                )])
            rows.append([InlineKeyboardButton("⬅️ Dashboard", callback_data="panel_home")])
            parts = [("game",), " GAME CONTROLS", chr(10), chr(10),
                     "Tap a game to enable or disable it."]
            await q.answer()
            await edit_prem(q.message, parts, reply_markup=InlineKeyboardMarkup(rows))
            return
        if d == "panel_deposits":
            pending = [
                (pid, pay) for pid, pay in (data.get("pending_pay") or {}).items()
                if pay.get("status") == "pending"
            ][-8:]
            parts = [("cash",), " PENDING DEPOSITS", chr(10), chr(10)]
            rows = []
            if not pending:
                parts.append("No deposits are waiting for review.")
            for pid, pay in reversed(pending):
                uid = str(pay.get("user_id", ""))
                player = data.get("users", {}).get(uid, {})
                name = ("@" + player["username"]) if player.get("username") else player.get("name", uid)
                amount = pay.get("amount")
                amount_text = f"₹{float(amount):.2f}" if amount is not None else "amount not supplied"
                parts.extend([f"{name} · {amount_text} · ref {pid}", chr(10)])
                if amount is None:
                    rows.append([
                        InlineKeyboardButton(f"✅ ₹{min_dep_val(data):.0f}", callback_data=f"appr_{pid}_{min_dep_val(data):.0f}"),
                        InlineKeyboardButton("✅ ₹500", callback_data=f"appr_{pid}_500"),
                        InlineKeyboardButton("❌ Reject", callback_data=f"rej_{pid}"),
                    ])
                else:
                    rows.append([
                        InlineKeyboardButton(f"✅ Approve ₹{float(amount):.0f}", callback_data=f"appr_{pid}_auto"),
                        InlineKeyboardButton("❌ Reject", callback_data=f"rej_{pid}"),
                    ])
            rows.append([InlineKeyboardButton("⬅️ Dashboard", callback_data="panel_home")])
            await q.answer()
            await edit_prem(q.message, parts, reply_markup=InlineKeyboardMarkup(rows))
            return
        if d == "panel_withdrawals":
            pending = [
                (wid, wd) for wid, wd in (data.get("pending_wd") or {}).items()
                if wd.get("status") == "pending"
            ][-8:]
            parts = [("bank",), " PENDING WITHDRAWALS", chr(10), chr(10)]
            rows = []
            if not pending:
                parts.append("No withdrawals are waiting for review.")
            for wid, wd in reversed(pending):
                uid = str(wd.get("user_id", ""))
                player = data.get("users", {}).get(uid, {})
                name = ("@" + player["username"]) if player.get("username") else player.get("name", uid)
                parts.extend([
                    f"{name} · ₹{float(wd.get('amount', 0) or 0):.2f} · {wd.get('upi', 'UPI not supplied')} · ref {wid}",
                    chr(10),
                ])
                rows.append([
                    InlineKeyboardButton("✅ Mark paid", callback_data=f"wdok_{wid}"),
                    InlineKeyboardButton("↩️ Reject + refund", callback_data=f"wdno_{wid}"),
                ])
            rows.append([InlineKeyboardButton("⬅️ Dashboard", callback_data="panel_home")])
            await q.answer()
            await edit_prem(q.message, parts, reply_markup=InlineKeyboardMarkup(rows))
            return
        if d == "panel_commands":
            parts = [
                ("crown",), " OWNER COMMANDS", chr(10), chr(10),
                "/panel · /admincommands · /boton · /botoff", chr(10),
                "/setminibet · /setmindeposit · /setupi", chr(10),
                "/offgame · /ongame · /allow · /disallow", chr(10),
                "/addbal · /cutbal · /announcement · /makecode", chr(10), chr(10),
                "Every panel action checks owner access again.",
            ]
            await q.answer()
            await edit_prem(q.message, parts, reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("⬅️ Dashboard", callback_data="panel_home"),
            ]]))
            return
        await q.answer("Unknown panel action.", show_alert=True)
        return

    if d == "help_show":
        await q.answer()
        await edit_prem(q.message, [
            ("spark",), " GAME COMMANDS", chr(10), chr(10),
            "/dice · /basket · /football · /bowl · /dart · /slot", chr(10),
            "/coin · /rps · /mines · /bj · /limbo · /7up", chr(10),
            "/wallet · /deposit · /withdraw · /mystats",
        ])
        return
    if d == "quick_dice":
        await q.message.reply_text("🎲 Try: /dice 50\nOr /dice 50 2 for 2d2w")
        return
    if d == "quick_bj":
        await q.message.reply_text("🃏 Try: /bj 20")
        return

    # ----- Mini games (DiceGamble-style cards) -----
    if d == "mini_crossy_play":
        await q.answer()
        await q.message.reply_text(
            "🐔 <b>Chicken Road</b>\n"
            "<blockquote>How to play\n"
            "• Tap <b>UP</b> to hop forward\n"
            "• Avoid cars &amp; trucks\n"
            "• Collect coins · reach the GOAL\n"
            "• 3 lives</blockquote>\n"
            "Bet: <code>/crossy 50</code> · <code>/crossy all</code>\n"
            "<i>Full mini-app coming — chat mode soon</i>",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🐔 Play for ₹50", callback_data="mini_crossy_bet_50"),
                 InlineKeyboardButton("📖 Rules", callback_data="mini_crossy_rules")],
                [InlineKeyboardButton("❌ Close", callback_data="mini_close")],
            ]),
        )
        return
    if d == "mini_crossy_rules":
        await q.answer()
        await q.message.reply_text(
            "🐔 <b>Chicken Road — Rules</b>\n"
            "<blockquote>"
            "Cross the road lane by lane.\n"
            "Hit by a vehicle = lose 1 life.\n"
            "0 lives = bet lost.\n"
            "Reach GOAL = win multiplier by lanes cleared.\n"
            "Coins boost payout slightly."
            "</blockquote>",
            parse_mode="HTML",
        )
        return
    if d.startswith("mini_crossy_bet_"):
        stake_s = d.replace("mini_crossy_bet_", "")
        await q.answer()
        await q.message.reply_text(
            f"🐔 Stake ₹{stake_s} locked for Chicken Road.\n"
            f"Use <code>/crossy {stake_s}</code> in group when chat mode is live.\n"
            f"<i>Or wait for mini-app button.</i>",
            parse_mode="HTML",
        )
        return
    if d == "mini_roulette_play":
        await q.answer()
        await q.message.reply_text(
            "🎡 <b>Roulette — quick start</b>\n"
            "<code>/roulette 50 red</code>\n"
            "<code>/roulette 50 black</code>\n"
            "<code>/roulette 50 odd</code>\n"
            "<code>/roulette 50 17</code> (exact 35×)",
            parse_mode="HTML",
        )
        return
    if d == "mini_roulette_rules":
        await q.answer()
        await q.message.reply_text(
            "🎡 <b>Roulette rules</b>\n"
            "Red/Black/Odd/Even/High/Low · ~1.95×\n"
            "Exact number 0–36 · 35×\n"
            "European wheel 0–36",
            parse_mode="HTML",
        )
        return
    if d == "mini_close":
        try:
            await q.message.delete()
        except Exception:
            await q.answer("Closed")
        return

    # ----- Admin help buttons -----
    if d.startswith("adm_"):
        data = load()
        if not is_owner(data, user.id) and user.id not in set(data.get("bot_admins") or []):
            await q.answer("Admin only", show_alert=True)
            return
        await q.answer()
        tips = {
            "adm_help_addbal": "➕ <code>/addbal USER_ID AMOUNT</code>\nExample: /addbal 8314045587 500",
            "adm_help_cutbal": "➖ <code>/cutbal USER_ID AMOUNT</code>",
            "adm_help_freeze": "❄️ <code>/freeze USER_ID</code>",
            "adm_help_unfreeze": "🔥 <code>/unfreeze USER_ID</code>",
            "adm_help_rig": "🎰 <code>/rigmode off|active|full</code>\nor /setlimits → Rig buttons",
            "adm_help_credit": "💰 <code>/creditbyamount 500.37</code>\nExact UPI unique amount",
            "adm_help_maxbet": "📈 <code>/setmaxbet 10000</code>",
            "adm_help_minbet": "📉 <code>/setminibet 50</code>",
            "adm_help_hb": "🏦 <code>/hb</code> (anyone)\n<code>/hbadd 1000</code> — owner, <b>DM only</b>",
            "adm_help_announce": "📢 <code>/announce Your message</code>",
            "adm_help_winsch": "🔗 In wins channel: <code>/setwinschannel</code>",
        }
        if d in tips:
            await q.message.reply_text(tips[d], parse_mode="HTML")
            return
        if d == "adm_run_setlimits":
            await cmd_setlimits(update, context)
            return
        if d == "adm_run_boton":
            data["settings"]["bot_on"] = True
            save(data)
            await q.message.reply_text("✅ Bot ON")
            return
        if d == "adm_run_botoff":
            data["settings"]["bot_on"] = False
            save(data)
            await q.message.reply_text("🛠 Bot OFF")
            return
        if d == "adm_run_panel":
            await cmd_panel(update, context)
            return
        if d == "adm_run_logs":
            await cmd_logs(update, context)
            return
        if d == "adm_close":
            try:
                await q.message.delete()
            except Exception:
                pass
            return
        return
    if d in ("mini_wheel_play", "mini_wheel_rules"):
        await q.answer()
        await q.message.reply_text(
            "🎡 <b>Wheel</b>\nUse <code>/wheel 50</code> when live.\n"
            "Spin multipliers: 0× · 0.5× · 1× · 1.5× · 2× · 5×",
            parse_mode="HTML",
        )
        return
    if d in ("mini_tower_rules", "mini_tower_play") or d.startswith("tower_"):
        await q.answer()
        await q.message.reply_text("🐵 Monkey Tower removed.")
        return
    if False and d == "mini_tower_rules":
        await q.answer()
        await q.message.reply_text(
            "🐵 <b>Monkey Tower — Rules</b>\n\n"
            "Each climb: chance to fall increases.\n"
            "Floor mult: 1.3x → 1.7x → 2.2x → 3x → 4x → 6x → 10x\n"
            "Fall = lose stake. Cash out anytime to take pot.\n"
            "Start: <code>/tower 50</code>",
            parse_mode="HTML",
        )
        return
    if d.startswith("tower_start_"):
        await q.answer()
        try:
            stake = float(d.replace("tower_start_", ""))
        except Exception:
            stake = 50
        context.args = [str(int(stake))]
        await cmd_tower(update, context)
        return
    if d.startswith("tower_climb_"):
        uid = d.replace("tower_climb_", "")
        if str(user.id) != uid:
            await q.answer("Not your game!", show_alert=True)
            return
        data = load()
        g = (data.get("tower_games") or {}).get(uid)
        if not g or not g.get("alive"):
            await q.answer("No active tower.", show_alert=True)
            return
        floor = int(g.get("floor", 0)) + 1
        # survival chance decreases with floor
        chance = max(0.25, 0.88 - floor * 0.07)
        rig = str(data.get("settings", {}).get("rig_mode", "off"))
        if rig == "full":
            chance *= 0.55
        elif rig == "active":
            chance *= 0.75
        import random as _r
        if _r.random() > chance:
            # fall
            stake = float(g.get("stake", 0))
            g["alive"] = False
            data["tower_games"][uid] = g
            u = ensure_user(data, user)
            record(data, user.id, "Tower", stake, False, 0)
            save(data)
            await q.edit_message_text(
                f"💥 <b>Fell at floor {floor}!</b>\n\n"
                f"Lost ₹{stake:.2f}\n"
                f"Try again: /tower {int(stake)}",
                parse_mode="HTML",
            )
            return
        # success — raise mult
        mults = [1.0, 1.30, 1.70, 2.20, 3.00, 4.00, 6.00, 10.00, 15.00]
        mult = mults[min(floor, len(mults) - 1)]
        g["floor"] = floor
        g["mult"] = mult
        data["tower_games"][uid] = g
        save(data)
        pot = round(float(g["stake"]) * mult, 2)
        B = InlineKeyboardButton
        await q.edit_message_text(
            f"🐵 <b>Floor {floor} cleared!</b>\n\n"
            f"Multiplier: <b>{mult:.2f}x</b>\n"
            f"Pot: ₹{pot:.2f}\n\n"
            f"Climb again or cash out.",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [B("🍌 Climb next", callback_data=f"tower_climb_{uid}")],
                [B(f"💰 Cash out ₹{pot:.2f}", callback_data=f"tower_cash_{uid}")],
            ]),
        )
        return
    if d.startswith("tower_cash_"):
        uid = d.replace("tower_cash_", "")
        if str(user.id) != uid:
            await q.answer("Not your game!", show_alert=True)
            return
        data = load()
        g = (data.get("tower_games") or {}).get(uid)
        if not g or not g.get("alive"):
            await q.answer("No active tower.", show_alert=True)
            return
        stake = float(g.get("stake", 0))
        mult = float(g.get("mult", 1))
        payout = round(stake * mult, 2)
        g["alive"] = False
        data["tower_games"][uid] = g
        add_bal(data, uid, payout)
        record(data, user.id, "Tower", stake, payout > stake, payout)
        save(data)
        await q.edit_message_text(
            f"💰 <b>Cashed out!</b>\n\n"
            f"Floor {int(g.get('floor', 0))} · {mult:.2f}x\n"
            f"Payout: <b>₹{payout:.2f}</b>\n"
            f"Balance: ₹{float(ensure_user(data, user).get('balance', 0)):.2f}",
            parse_mode="HTML",
        )
        return
    if d == "mini_tower_play":
        await q.answer()
        context.args = ["50"]
        await cmd_tower(update, context)
        return

    if d.startswith("betagain_"):
        parts = d.split("_")
        # betagain_game_stake_rule_rounds
        if len(parts) >= 5:
            gkey, stake_s, rule, rounds_s = parts[1], parts[2], parts[3], parts[4]
            try:
                st = float(stake_s)
                rd = int(rounds_s)
            except Exception:
                await q.answer("Invalid", show_alert=True)
                return
            # reuse ask_mode flow
            try:
                await q.answer()
                await ask_mode(update, context, gkey, st, rule=rule, rounds=rd)
            except Exception as e:
                await q.message.reply_text(f"Try /{gkey} {int(st)}")
        return
    if d == "jp_join":
        if not has_nova_tag(user):
            await q.answer("Add @HRCasino to your name!", show_alert=True)
            return
        u = data["users"][str(user.id)]
        if int(u.get("bets", 0)) < 10:
            await q.answer(f"Complete 10 games first! {u.get('bets',0)}/10", show_alert=True)
            return
        jp = data.setdefault("jackpot", {"joined": []})
        uid = str(user.id)
        if uid in jp.get("joined", []):
            await q.answer("Already joined!", show_alert=True)
            return
        jp.setdefault("joined", []).append(uid)
        save(data)
        await q.answer("Joined!", show_alert=True)
        try:
            await q.message.reply_text(f"✅ {user.first_name} joined Daily Jackpot 🎰")
        except Exception:
            pass
        return
    if d == "jp_how":
        await q.answer()
        try:
            await reply_prem(q.message, [
                ("gift",), " Jackpot rules", nl if False else chr(10),
                "0.1% of every bet goes to the pool", chr(10),
                "Join: add @HRCasino to name + 10 games", chr(10),
                "Owner draws with /jackpotdraw",
            ])
        except Exception:
            pass
        return
    if d.startswith("esc_acc_"):
        eid = d.split("esc_acc_", 1)[1]
        esc = data.get("escrows", {}).get(eid)
        if not esc or esc.get("status") != "pending":
            await q.answer("Invalid", show_alert=True)
            return
        if user.id != int(esc["to"]):
            await q.answer("Not your escrow", show_alert=True)
            return
        esc["status"] = "active"
        save(data)
        await q.answer("Accepted")
        kb = InlineKeyboardMarkup([[
            InlineKeyboardButton("Release", callback_data=f"esc_rls_{eid}"),
            InlineKeyboardButton("Refund", callback_data=f"esc_ref_{eid}"),
            InlineKeyboardButton("Cancel", callback_data=f"esc_dec_{eid}"),
        ]])
        msg = (
            f"✅ <b>Escrow ACTIVE</b> #{eid}\n"
            f"💰 ₹{float(esc['amount']):.0f} locked\n\n"
            f"Release → receiver | Refund → sender | Cancel"
        )
        try:
            await q.edit_message_caption(caption=msg, parse_mode="HTML", reply_markup=kb)
        except Exception:
            try:
                await q.edit_message_text(msg, parse_mode="HTML", reply_markup=kb)
            except Exception:
                pass
        return

    if d.startswith("esc_dec_"):
        eid = d.split("esc_dec_", 1)[1]
        esc = data.get("escrows", {}).get(eid)
        if not esc or esc.get("status") != "pending":
            await q.answer("Invalid", show_alert=True)
            return
        if user.id not in (int(esc["to"]), int(esc["from"])):
            await q.answer("Not allowed", show_alert=True)
            return
        add_bal(data, str(esc["from"]), float(esc["amount"]))
        esc["status"] = "cancelled"
        save(data)
        await q.answer("Declined")
        try:
            await q.edit_message_text(f"❌ Escrow #{eid} cancelled")
        except Exception:
            pass
        return

    if d.startswith("esc_rls_"):
        eid = d.split("esc_rls_", 1)[1]
        esc = data.get("escrows", {}).get(eid)
        if not esc or esc.get("status") not in ("pending", "active"):
            await q.answer("Invalid", show_alert=True)
            return
        if user.id != int(esc["from"]) and not is_owner(data, user.id):
            await q.answer("Sirf sender / owner RLS kar sake", show_alert=True)
            return
        add_bal(data, str(esc["to"]), float(esc["amount"]))
        esc["status"] = "released"
        save(data)
        await q.answer("Released")
        try:
            await q.edit_message_caption(caption=f"🔓 RLS #{eid} · ₹{esc['amount']:.0f} receiver ko")
        except Exception:
            try:
                await q.edit_message_text(f"🔓 RLS #{eid} · ₹{esc['amount']:.0f} receiver ko")
            except Exception:
                pass
        return
    if d.startswith("esc_ref_"):
        eid = d.split("esc_ref_", 1)[1]
        esc = data.get("escrows", {}).get(eid)
        if not esc or esc.get("status") not in ("pending", "active"):
            await q.answer("Invalid", show_alert=True)
            return
        if user.id not in (int(esc["from"]), int(esc["to"])) and not is_owner(data, user.id):
            await q.answer("Not allowed", show_alert=True)
            return
        add_bal(data, str(esc["from"]), float(esc["amount"]))
        esc["status"] = "refunded"
        save(data)
        await q.answer("Refunded")
        try:
            await q.edit_message_text(f"💸 Refund #{eid} · ₹{esc['amount']:.0f} sender ko")
        except Exception:
            pass
        return

    
    if d.startswith("tipok_"):
        # tipok_{from}_{to}_{amount}
        parts = d.split("_")
        if len(parts) < 4:
            return
        if str(user.id) != parts[1]:
            await q.answer("Not your tip", show_alert=True)
            return
        to_id, amt = parts[2], float(parts[3])
        data2 = load()
        data2.get("pending_tips", {}).pop(str(user.id), None)
        if not take_bal(data2, str(user.id), amt):
            await q.answer("Low balance", show_alert=True)
            try:
                await q.edit_message_text("❌ Tip cancelled — low balance")
            except Exception:
                pass
            return
        if str(to_id) not in data2.get("users", {}):
            data2.setdefault("users", {})[str(to_id)] = {
                "balance": 0.0, "ref_code": rid("R"), "wagered": 0.0, "won": 0.0, "lost": 0.0, "bets": 0,
                "username": "", "name": str(to_id), "joined": str(date.today()),
            }
        add_bal(data2, str(to_id), amt)
        save(data2)
        from_tag = ("@" + user.username) if user.username else (user.first_name or "Someone")
        try:
            await q.edit_message_text(f"✅ Tip Sent!\nTo: {to_id}\nAmount: ₹{amt:.0f}")
        except Exception:
            pass
        try:
            bal = float(data2["users"][str(to_id)]["balance"])
            await context.bot.send_message(
                int(to_id),
                f"🏆 You received a tip!\n\nFrom: {from_tag}\n💰 Amount: ₹{amt:.0f} added!\n🏦 New Balance: ₹{bal:.2f}\n\nUse /wallet to view.",
            )
        except Exception:
            pass
        return
    if d.startswith("tipno_"):
        if str(user.id) != d.split("_")[1]:
            await q.answer("Not your tip", show_alert=True)
            return
        data2 = load()
        data2.get("pending_tips", {}).pop(str(user.id), None)
        save(data2)
        try:
            await q.edit_message_text("❌ Tip declined.")
        except Exception:
            pass
        return

    if d.startswith("rain_"):
        rid_rain = d.split("_", 1)[1]
        rain = data.get("rains", {}).get(rid_rain)
        if not rain or not rain.get("active"):
            await q.answer("Rain khatam / invalid", show_alert=True)
            return
        uid = str(user.id)
        if uid in rain.get("claimed", []):
            await q.answer("Already claimed!", show_alert=True)
            return
        if len(rain.get("claimed", [])) >= int(rain["slots"]):
            await q.answer("Slots full!", show_alert=True)
            return
        # Must have @HRCasino in display name / username
        full_name = " ".join(filter(None, [
            user.first_name or "",
            user.last_name or "",
            user.username or "",
        ]))
        tag = "novaversebet"
        if tag not in full_name.lower().replace(" ", ""):
            await q.answer(
                "Sirf unke liye jinke name mein @HRCasino ho!",
                show_alert=True,
            )
            return
        ensure_user(data, user)
        u = data["users"][uid]
        games = int(u.get("bets", 0) or 0)
        if games < 10:
            await q.answer(
                f"First 10 games khelo! Abhi: {games}/10",
                show_alert=True,
            )
            return
        each = float(rain["each"])
        rain.setdefault("claimed", []).append(uid)
        add_bal(data, uid, each)
        save(data)
        await q.answer(f"+₹{each:.0f} claimed!", show_alert=True)
        left = int(rain["slots"]) - len(rain["claimed"])
        names = []
        for cid in rain["claimed"]:
            uu = data["users"].get(cid, {})
            names.append(uu.get("name") or uu.get("username") or cid)
        if left <= 0:
            rain["active"] = False
            save(data)
            winners = "\n".join(f"✅ {n}" for n in names)
            try:
                await q.edit_message_text(
                    f"🌧️ *RAIN KHATAM*\n"
                    f"💰 Total ₹{rain['total']:.0f}\n\n"
                    f"*Winners:*\n{winners}",
                    parse_mode="Markdown",
                )
            except Exception:
                await q.message.reply_text(
                    f"🌧️ *RAIN KHATAM*\nWinners:\n{winners}",
                    parse_mode="Markdown",
                )
        else:
            kb = InlineKeyboardMarkup([[
                InlineKeyboardButton(
                    f"🌧️ Claim ₹{each:.0f} ({left}/{rain['slots']})",
                    callback_data=f"rain_{rid_rain}",
                )
            ]])
            try:
                await q.edit_message_reply_markup(reply_markup=kb)
            except Exception:
                pass
        return


    if d.startswith("wdok_") or d.startswith("wdno_"):
        if not is_owner(data, user.id):
            await q.answer("Owner only", show_alert=True)
            return
        wid = d.split("_", 1)[1]
        wd = data.get("pending_wd", {}).get(wid)
        if not wd or wd.get("status") != "pending":
            await q.answer("Already done", show_alert=True)
            return
        if d.startswith("wdok_"):
            wd["status"] = "paid"
            save(data)
            try:
                await context.bot.send_message(wd["user_id"], f"✅ Withdraw ₹{wd['amount']:.0f} paid on `{wd['upi']}`", parse_mode="Markdown")
            except Exception:
                pass
            await q.edit_message_text((q.message.text or "") + "\n\n✅ PAID")
        else:
            wd["status"] = "rejected"
            add_bal(data, str(wd["user_id"]), float(wd["amount"]))
            save(data)
            try:
                await context.bot.send_message(wd["user_id"], f"❌ Withdraw rejected — ₹{wd['amount']:.0f} refunded")
            except Exception:
                pass
            await q.edit_message_text((q.message.text or "") + "\n\n❌ REJECTED + refund")
        return

    if d == "pay_done":
        if q.message.chat.type != "private":
            await q.answer("DM only", show_alert=True)
            return
        await q.answer()
        data = load()
        uid = str(user.id)
        dep = (data.get("pending_dep_step") or {}).get(uid) or {}
        unique_amt = dep.get("unique_amt")
        base_amt = dep.get("amount")
        method = dep.get("method", "upi")
        network = dep.get("network", "")
        # Notify all owners for quick credit
        note = (
            f"💳 <b>DEPOSIT CLAIM</b>\n"
            f"User: <code>{uid}</code> @{user.username or '-'}\n"
            f"Method: {method} {network}\n"
        )
        if unique_amt:
            note += f"Unique amount: <b>₹{float(unique_amt):.2f}</b>\nBase: ₹{float(base_amt or 0):.0f}\n"
            note += f"Owner credit: <code>/creditbyamount {float(unique_amt):.2f}</code>\n"
        note += "Waiting for screenshot / bank confirm."
        for oid in owners(data):
            try:
                await context.bot.send_message(oid, note, parse_mode="HTML")
            except Exception:
                pass
        await q.message.reply_text(
            "📸 <b>Payment marked</b>\n"
            "<blockquote>"
            "Ab screenshot yahi bhejo (no caption needed).\n"
            "Admin ko alert gaya — unique amount se match hoga.\n"
            "</blockquote>",
            parse_mode="HTML",
        )
        return

    if d.startswith("drpick_"):
        parts = d.split("_")
        mode, stake_s, oid = parts[1], parts[2], int(parts[3])
        if user.id != oid:
            await q.answer("🚫 This is not your game!", show_alert=True)
            return
        if mode not in ("high", "low", "odd", "even"):
            await q.answer("Invalid pick", show_alert=True)
            return
        stake = float(stake_s)
        u = ensure_user(data, user)
        if float(u.get("balance", 0)) < stake:
            await q.answer("Insufficient balance", show_alert=True)
            return
        if not take_bal(data, str(user.id), stake):
            return
        save(data)
        await q.answer("Rolling...")
        try:
            await q.edit_message_text(f"🎲 DR • {mode.upper()} • ₹{stake:.0f}")
        except Exception:
            pass
        class _Fake:
            message = q.message
            callback_query = q
        await _finish_dr(update, context, data, user, stake, mode)
        return

    if d.startswith("rule_"):
        parts = d.split("_")
        # rule_crazy_dice_50_USERID_ROUNDS
        rule, game_key, stake_s = parts[1], parts[2], parts[3]
        owner_id = int(parts[4]) if len(parts) > 4 else user.id
        rounds = int(parts[5]) if len(parts) > 5 else 1
        if user.id != owner_id:
            await q.answer("🚫 This is not your game!", show_alert=True)
            return
        await ask_mode_from_cb(q, context, data, user, game_key, float(stake_s), rule, rounds)
        return

    if d.startswith("mode_bot_"):
        # mode_bot_{rule}_{game}_{stake}_{owner}_{rounds}
        try:
            parts = d.split("_")
            rule = parts[2]
            game_key = parts[3]
            stake = float(parts[4])
            owner_id = int(parts[5]) if len(parts) > 5 else user.id
            rounds = int(parts[6]) if len(parts) > 6 else 1
        except Exception:
            await q.answer("Invalid button", show_alert=True)
            return
        if user.id != owner_id:
            await q.answer("This is not your game!", show_alert=True)
            return
        data = load()
        ensure_user(data, user)
        emoji, label = GAMES.get(game_key, ("🎲", game_key))
        uid = str(user.id)
        if uid in data.get("pending_bets", {}):
            await q.answer("Finish your current game first!", show_alert=True)
            return
        bal = float(data.get("users", {}).get(uid, {}).get("balance", 0) or 0)
        if bal < stake:
            try:
                await q.answer("Low balance — deposit first", show_alert=True)
            except Exception:
                pass
            try:
                me = await context.bot.get_me()
                kb = InlineKeyboardMarkup([[
                    InlineKeyboardButton("⬇️ Deposit Now", url=f"https://t.me/{me.username}?start=deposit"),
                ]])
                await q.message.reply_text(
                    f"💵 Balance too low — top up to keep playing!\nNeed ₹{stake:.0f} · You have ₹{bal:.0f}",
                    reply_markup=kb,
                )
            except Exception:
                pass
            return
        if not take_bal(data, uid, stake):
            await q.answer("Low balance", show_alert=True)
            return
        bid = rid()
        # always correct emoji for game (dart=🎯 bowl=🎳 etc.)
        emoji, label = GAMES.get(game_key, (emoji, label))
        data.setdefault("pending_bets", {})[uid] = {
            "bet_id": bid,
            "game": game_key,
            "label": label,
            "emoji": emoji,
            "stake": stake,
            "vs": "bot",
            "rule": rule,
            "user_vals": [],
            "time": time.time(),
            "rounds": max(1, rounds),
            "need": need_wins_for(rounds),
        }
        save(data)
        rule_txt = "lowest total wins" if rule == "crazy" else "highest total wins"
        uname = user.username or user.first_name or "Player"
        msg = (
            f"<b>{emoji} {label} vs Bot #{bid}</b>\n\n"
            f"<blockquote>"
            f"💰 Stake: ₹{int(stake)}\n"
            f"{'⚡ Crazy — ' if rule=='crazy' else '🔄 '}{rule_txt}\n"
            f"👤 {uname} — send {emoji} now"
            f"</blockquote>\n\n"
            f"Open emoji panel → {label}"
        )
        try:
            await q.edit_message_text(msg, parse_mode="HTML")
        except Exception:
            try:
                await q.message.reply_text(msg, parse_mode="HTML")
            except Exception:
                try:
                    await q.message.reply_text(f"{label} vs Bot #{bid}\n₹{int(stake)}\nSend {emoji}")
                except Exception:
                    pass
        try:
            await q.answer("Game started!")
        except Exception:
            pass
        return

    if d.startswith("mode_pvp_"):
        parts = d.split("_")
        rule, game_key, stake_s = parts[2], parts[3], parts[4]
        owner_id = int(parts[5]) if len(parts) > 5 else user.id
        rounds = int(parts[6]) if len(parts) > 6 else 1
        if user.id != owner_id:
            await q.answer("🚫 This is not your game!", show_alert=True)
            return
        stake = float(stake_s)
        emoji, label = GAMES.get(game_key, ("🎲", game_key))
        pid = rid()
        data.setdefault("pvp", {})[pid] = {
            "id": pid,
            "game": game_key,
            "label": label,
            "emoji": emoji,
            "stake": stake,
            "rule": rule,
            "a": user.id,
            "b": None,
            "a_val": None,
            "b_val": None,
            "locked": False,
            "status": "wait_accept",
            "time": time.time(),
            "chat_id": q.message.chat_id,
            "rounds": rounds,
            "need": need_wins_for(rounds),
            "a_score": 0,
            "b_score": 0,
            "played": 0,
        }
        save(data)
        rule_txt = "lower score wins" if rule == "crazy" else "higher score wins"
        icon = "⚡" if rule == "crazy" else "📈"
        kb = InlineKeyboardMarkup([[
            style_btn("✅ Accept PvP", style="success", callback_data=f"pvp_acc_{pid}"),
            style_btn("❌", style="danger", callback_data=f"pvp_dec_{pid}"),
        ]])
        await q.edit_message_text(
            f"<b>{icon} {rule.title()} {label} PvP #{pid}</b>\n\n"
            f"<blockquote>"
            f"💰 Stake: ₹{stake:.0f}\n"
            f"👤 Host: {user.first_name}\n"
            f"📜 Rule: {rule_txt}\n"
            f"⏳ Waiting for opponent…"
            f"</blockquote>\n\n"
            f"Tap Accept to join:",
            parse_mode="HTML",
            reply_markup=kb,
        )
        return

    if d.startswith("pvp_acc_"):
        data = load()
        pid = d.split("_", 2)[2]
        ch = data.get("pvp", {}).get(pid)
        if not ch or ch.get("status") != "wait_accept":
            await q.answer("Expired", show_alert=True)
            return
        if ch["a"] == user.id:
            await q.answer("You cannot accept your own challenge", show_alert=True)
            return
        stake = float(ch["stake"])
        a_uid, b_uid = str(ch["a"]), str(user.id)
        if a_uid not in data["users"]:
            await q.edit_message_text("Host account missing")
            return
        ensure_user(data, user)
        a_bal = float(data["users"].get(a_uid, {}).get("balance", 0) or 0)
        b_bal = float(data["users"].get(b_uid, {}).get("balance", 0) or 0)
        if a_bal < stake:
            # host short — notify host, don't cancel for accepter wrongly
            try:
                me = await context.bot.get_me()
                kb = InlineKeyboardMarkup([[
                    InlineKeyboardButton("⬇️ Deposit Now", url=f"https://t.me/{me.username}?start=deposit"),
                ]])
                await context.bot.send_message(
                    int(a_uid),
                    f"💵 Balance too low for PvP (₹{stake:.0f}).\nYou have ₹{a_bal:.0f} — deposit to play.",
                    reply_markup=kb,
                )
            except Exception:
                pass
            await q.answer("Host has low balance", show_alert=True)
            return
        if b_bal < stake:
            try:
                me = await context.bot.get_me()
                kb = InlineKeyboardMarkup([[
                    InlineKeyboardButton("⬇️ Deposit Now", url=f"https://t.me/{me.username}?start=deposit"),
                ]])
                await q.message.reply_text(
                    f"💵 Balance too low — top up to keep playing!\nNeed ₹{stake:.0f} · You have ₹{b_bal:.0f}",
                    reply_markup=kb,
                )
            except Exception:
                pass
            await q.answer("You need more balance", show_alert=True)
            return
        take_bal(data, a_uid, stake)
        take_bal(data, b_uid, stake)
        ch["b"] = user.id
        ch["locked"] = True
        ch["status"] = "wait_emoji"
        ch["a_vals"] = []
        ch["b_vals"] = []
        ch["a_val"] = None
        ch["b_val"] = None
        save(data)
        emoji = ch.get("emoji", "🎲")
        rule = ch.get("rule", "crazy")
        rule_txt = "lower score wins" if rule == "crazy" else "higher score wins"
        icon = "⚡" if rule == "crazy" else "📈"
        rnds = int(ch.get("rounds") or 1)
        await q.edit_message_text(
            f"{icon} *{rule.title()} PvP* #{pid} LIVE\n"
            f"₹{stake:.0f} each locked · {rnds} throw(s)\n"
            f"Rule: *{rule_txt}* (totals compared)\n\n"
            f"Both players send {emoji} ×{rnds}",
            parse_mode="Markdown",
        )
        return

    if d.startswith("pvp_dec_"):
        pid = d.split("_", 2)[2]
        ch = data.get("pvp", {}).get(pid)
        if ch and ch.get("status") == "wait_accept":
            data["pvp"].pop(pid, None)
            save(data)
            await q.edit_message_text("Declined.")
        return


    if d.startswith("bj_hit_"):
        tid = int(d.split("_")[2])
        if user.id != tid:
            await q.answer("This is not your game!", show_alert=True)
            return
        game = data.get("bj", {}).get(str(user.id))
        if not game or game.get("done"):
            await q.answer("No game", show_alert=True)
            return
        game["player"].append(bj_draw())
        pv = bj_hand_value(game["player"])
        save(data)
        if pv > 21:
            await bj_finish(q, context, data, user, stand=True)
            return
        kb = InlineKeyboardMarkup([[
            InlineKeyboardButton("🃏 HIT", callback_data=f"bj_hit_{user.id}"),
            InlineKeyboardButton("🛑 STAND", callback_data=f"bj_stand_{user.id}"),
        ]])
        dealer = game["dealer"]
        stake = float(game["stake"])
        try:
            img_path = make_bj_card(
                game["player"], dealer, pv, 0, stake,
                "HIT or STAND?", f"Bet Rs {stake:.0f}", hide_dealer=True,
            )
            try:
                await q.message.delete()
            except Exception:
                pass
            await context.bot.send_photo(
                chat_id=q.message.chat_id,
                photo=open(img_path, "rb"),
                caption=f"🃏 BLACKJACK · ₹{stake:.0f}\nHIT or STAND?",
                reply_markup=kb,
            )
        except Exception as e:
            logger.warning("bj hit img %s", e)
            await context.bot.send_message(
                q.message.chat_id,
                f"🃏 BLACKJACK · ₹{stake:.0f}\nYou: {bj_fmt(game['player'])} ({pv})\nHIT or STAND?",
                reply_markup=kb,
            )
        return

    if d.startswith("bj_stand_"):
        tid = int(d.split("_")[2])
        if user.id != tid:
            await q.answer("This is not your game!", show_alert=True)
            return
        await bj_finish(q, context, data, user, stand=True)
        return

    if d.startswith("bj_again_"):
        if not is_target_group(update):
            await q.answer("Group only", show_alert=True)
            return
        stake = float(d.split("_")[2])
        # reuse by editing message prompt
        u = ensure_user(data, user)
        if float(u.get("balance", 0)) < stake:
            await q.answer("Insufficient balance", show_alert=True)
            return
        # start new bj silently via message
        class Fake:
            pass
        fake = Fake()
        fake.message = q.message
        fake.effective_user = user
        fake.effective_chat = q.message.chat
        fake.callback_query = None
        context.args = [str(int(stake))]
        await cmd_bj(fake, context)
        return

    if d.startswith("rps_"):
        parts = d.split("_")
        choice, stake = parts[1], float(parts[2])
        u = data["users"][str(user.id)]
        if float(u.get("balance", 0)) < stake:
            await q.edit_message_text("Insufficient balance")
            return
        bot_c = secrets.choice(["rock", "paper", "scissors"])
        wins = {("rock", "scissors"), ("scissors", "paper"), ("paper", "rock")}
        if choice == bot_c:
            await q.edit_message_text(f"You {choice} vs Bot {bot_c}\n🤝 Draw")
            return
        win = (choice, bot_c) in wins
        take_bal(data, str(user.id), stake)
        payout = round(stake * 1.85, 2) if win else 0
        if win:
            add_bal(data, str(user.id), payout)
        record(data, user.id, "RPS", stake, win, payout)
        save(data)
        await q.edit_message_text(
            f"You *{choice}* vs Bot *{bot_c}*\n"
            + ("🏆 Won" if win else "❌ Lost")
            + f"\n💰 ₹{float(data['users'][str(user.id)]['balance']):.0f}",
            parse_mode="Markdown",
        )
        return

    if d.startswith("coinflip_"):
        parts = d.split("_")
        if len(parts) >= 4:
            side, stake_s, oid = parts[1], parts[2], int(parts[3])
            if user.id != oid:
                await q.answer("Not your game", show_alert=True)
                return
            if side not in ("heads", "tails"):
                await q.answer("Invalid", show_alert=True)
                return
            stake = float(stake_s)
            u = ensure_user(data, user)
            if float(u.get("balance", 0) or 0) < stake:
                await q.answer("Low balance", show_alert=True)
                return
            if not take_bal(data, str(user.id), stake):
                await q.answer("Low balance", show_alert=True)
                return
            save(data)
            try:
                await q.edit_message_text(f"🪙 Coin Flip · ₹{int(stake)} · {side.upper()}")
            except Exception:
                pass
            await finish_coin(q.message, context, data, user, stake, side)
        return

    if d.startswith("mine25_"):
        parts = d.split("_")
        if len(parts) >= 3:
            tile, oid = int(parts[1]), parts[2]
            if str(q.from_user.id) != oid:
                await q.answer("Not your game", show_alert=True)
                return
            data = load()
            g = (data.get("mines_games") or {}).get(oid)
            if not g or not g.get("alive"):
                await q.answer("Game over", show_alert=True)
                return
            if tile in g.get("revealed", []):
                await q.answer("Already open", show_alert=True)
                return
            if tile in g.get("bombs", []):
                g["alive"] = False
                data["mines_games"].pop(oid, None)
                record(data, oid, "Mines", float(g.get("stake", 0) or 0), False, 0)
                save(data)
                await q.answer("BOOM!", show_alert=True)
                try:
                    await q.edit_message_text(f"💣 Mine hit! Lost ₹{float(g['stake']):.0f}")
                except Exception:
                    pass
                return
            g.setdefault("revealed", []).append(tile)
            g["mult"] = round(1.0 + 0.35 * len(g["revealed"]), 2)
            save(data)
            await q.answer(f"Safe! x{g['mult']}")
            rows = []
            for r in range(5):
                row = []
                for c in range(5):
                    n = r * 5 + c + 1
                    if n in g["revealed"]:
                        row.append(InlineKeyboardButton("✅", callback_data="noop"))
                    else:
                        row.append(InlineKeyboardButton("⬜", callback_data=f"mine25_{n}_{oid}"))
                rows.append(row)
            rows.append([InlineKeyboardButton(f"💰 Cash Out x{g['mult']}", callback_data=f"minecash_{oid}")])
            try:
                await q.edit_message_reply_markup(InlineKeyboardMarkup(rows))
            except Exception:
                pass
        return

    if d.startswith("minecash_"):
        oid = d.split("_")[1]
        if str(q.from_user.id) != oid:
            await q.answer("Not your game", show_alert=True)
            return
        data = load()
        g = (data.get("mines_games") or {}).pop(oid, None)
        if not g or not g.get("alive"):
            await q.answer("Nothing to cash", show_alert=True)
            return
        win = round(float(g["stake"]) * float(g.get("mult", 1)), 2)
        add_bal(data, oid, win)
        record(data, oid, "Mines", float(g["stake"]), True, win)
        save(data)
        try:
            await q.edit_message_text(f"💰 Cashed out! +₹{win:.0f} (x{g.get('mult')})")
        except Exception:
            pass
        return

    if d == "noop":
        await q.answer()
        return

    if d.startswith("mine_"):
        parts = d.split("_")
        tile, stake, bomb = int(parts[1]), float(parts[2]), int(parts[3])
        uid = str(user.id)
        if not take_bal(data, uid, stake):
            await q.edit_message_text("Insufficient balance")
            return
        win = tile != bomb
        payout = round(stake * 1.8, 2) if win else 0
        if win:
            add_bal(data, uid, payout)
        record(data, user.id, "Mines", stake, win, payout)
        save(data)
        tiles = " ".join(["💥" if i == bomb else ("✅" if i == tile else "⬜") for i in range(1, 6)])
        await q.edit_message_text(
            f"💣 {tiles}\n" + ("🏆 Safe!" if win else "💥 Boom!") + f"\n💰 ₹{float(data['users'][uid]['balance']):.0f}"
        )
        return

    # payment approve (reload data so buttons always work)
    if d.startswith("appr_") or d.startswith("rej_"):
        data = load()
        if not is_owner(data, user.id):
            try:
                await q.answer("Owner only", show_alert=True)
            except Exception:
                pass
            return
        try:
            await q.answer("✅ OK")
        except Exception:
            pass
        parts = d.split("_")
        if d.startswith("rej_"):
            pid = parts[1]
            pay = data.get("pending_pay", {}).get(pid)
            if not pay or pay.get("status") != "pending":
                try:
                    await q.answer("Already handled", show_alert=True)
                except Exception:
                    pass
                return
            pay["status"] = "rejected"
            save(data)
            try:
                await context.bot.send_message(int(pay["user_id"]), "❌ Deposit rejected")
            except Exception:
                pass
            cap = (q.message.caption or q.message.text or "") + "\n❌ REJECTED"
            try:
                if q.message.photo:
                    await q.edit_message_caption(caption=cap)
                else:
                    await q.edit_message_text(cap)
            except Exception:
                pass
            return
        pid = parts[1]
        pay = data.get("pending_pay", {}).get(pid)
        if not pay or pay.get("status") != "pending":
            try:
                await q.answer("Already done", show_alert=True)
            except Exception:
                pass
            return
        amt = pay.get("amount")
        if len(parts) >= 3 and parts[2] not in ("auto", ""):
            try:
                amt = float(parts[2])
            except Exception:
                pass
        if amt is None:
            try:
                await q.answer("Pick amount button (50/100/…)", show_alert=True)
            except Exception:
                pass
            return
        try:
            amt = float(amt)
        except Exception:
            await q.answer("Invalid amount", show_alert=True)
            return
        if amt < min_dep_val(data):
            try:
                await q.answer(f"Min ₹{min_dep_val(data):.0f}", show_alert=True)
            except Exception:
                pass
            return
        pay["status"] = "approved"
        pay["amount"] = amt
        try:
            log_payment(data, "deposit", pay.get("user_id", 0), amt, "approved")
        except Exception:
            pass
        ensure_user(data, type("U", (), {"id": int(pay["user_id"]), "username": "", "first_name": "P"})())
        add_bal(data, str(pay["user_id"]), amt)
        data.setdefault("stats", {})
        data["stats"]["deposits"] = int(data["stats"].get("deposits", 0) or 0) + 1
        # track deposited on user
        try:
            data["users"][str(pay["user_id"])]["deposited"] = float(data["users"][str(pay["user_id"])].get("deposited", 0) or 0) + amt
        except Exception:
            pass
        save(data)
        try:
            await context.bot.send_message(int(pay["user_id"]), f"✅ Deposit approved +₹{amt:.0f}")
        except Exception:
            pass
        cap = (q.message.caption or q.message.text or "") + f"\n✅ APPROVED ₹{amt:.0f}"
        try:
            if q.message.photo:
                await q.edit_message_caption(caption=cap)
            else:
                await q.edit_message_text(cap)
        except Exception:
            pass
        return


# ---------- DICE / EMOJI HANDLER ----------
async def on_dice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.dice:
        return
    data = load()
    user = update.effective_user
    uid = str(user.id)
    emoji = update.message.dice.emoji
    value = int(update.message.dice.value)

    # ----- DiceGamble live match turns -----
    live = data.get("dice_live") or {}
    my_match = None
    mid = None
    for k, m in live.items():
        if int(m.get("turn") or 0) == user.id and emoji == "🎲":
            my_match, mid = m, k
            break
    if my_match and mid:
        need_rolls = int(my_match.get("rolls") or 1)
        rolls = list(my_match.get("turn_rolls") or [])
        rolls.append(value)
        my_match["turn_rolls"] = rolls
        if len(rolls) < need_rolls:
            data["dice_live"][mid] = my_match
            save(data)
            left = need_rolls - len(rolls)
            await update.message.reply_text(
                f"🎲 Roll {len(rolls)}/{need_rolls} · send 🎲 ×{left} more"
            )
            return
        # complete turn sum
        turn_sum = sum(rolls)
        my_match["turn_rolls"] = []
        p1, p2 = int(my_match["p1"]), int(my_match["p2"])
        is_p1 = user.id == p1
        # store this player's sum for the round
        if is_p1:
            my_match["r1"] = turn_sum
        else:
            my_match["r2"] = turn_sum
        # vs bot: auto bot rolls after p1
        if my_match.get("vs_bot") and is_p1:
            bot_rolls = [secrets.randbelow(6) + 1 for _ in range(need_rolls)]
            # visual bot dice
            for _ in range(need_rolls):
                try:
                    dm = await update.message.reply_dice(emoji="🎲")
                    await asyncio.sleep(3.2)
                    bot_rolls[bot_rolls.index(bot_rolls[_]) if False else _] = int(dm.dice.value) if _ < 1 else bot_rolls[_]
                except Exception:
                    pass
            # simpler: use last reply_dice values
            bot_vals = []
            for _ in range(need_rolls):
                try:
                    dm = await update.message.reply_dice(emoji="🎲")
                    await asyncio.sleep(3.3)
                    bot_vals.append(int(dm.dice.value))
                except Exception:
                    bot_vals.append(secrets.randbelow(6) + 1)
            my_match["r2"] = sum(bot_vals)
            my_match["n2"] = "Bot"
        # if both have rolled this exchange (p2 present and r1+r2 set, or vs_bot done)
        if my_match.get("r1") is not None and my_match.get("r2") is not None:
            s1, s2 = int(my_match["r1"]), int(my_match["r2"])
            crazy = bool(my_match.get("crazy"))
            if s1 == s2:
                point = "tie"
            elif crazy:
                point = "p1" if s1 < s2 else "p2"
            else:
                point = "p1" if s1 > s2 else "p2"
            if point == "p1":
                my_match["s1"] = int(my_match.get("s1") or 0) + 1
            elif point == "p2":
                my_match["s2"] = int(my_match.get("s2") or 0) + 1
            my_match["r1"] = None
            my_match["r2"] = None
            pts = int(my_match.get("pts") or 2)
            n1, n2 = my_match.get("n1") or "P1", my_match.get("n2") or "P2"
            await update.message.reply_text(
                f"<blockquote>🎲 Score\n"
                f"{n1}: {my_match['s1']}\n"
                f"{n2}: {my_match['s2']}\n"
                f"Last: {n1} {s1} · {n2} {s2}"
                f"{' (tie)' if point=='tie' else ''}</blockquote>",
                parse_mode="HTML",
            )
            if my_match["s1"] >= pts or my_match["s2"] >= pts:
                # game over — winner gets stake * DICE_WIN_MULT (stake already deducted)
                stake = float(my_match.get("stake") or 0)
                win_amt = round(stake * DICE_WIN_MULT, 2)
                if my_match["s1"] >= pts:
                    winner_id, wname = p1, n1
                else:
                    winner_id, wname = p2, n2
                if my_match.get("vs_bot"):
                    if winner_id == p1:
                        add_bal(data, str(p1), win_amt)
                        record(data, str(p1), "dice", stake, True, win_amt)
                    else:
                        record(data, str(p1), "dice", stake, False, 0)
                else:
                    if winner_id == p1:
                        add_bal(data, str(p1), win_amt)
                        record(data, str(p1), "dice", stake, True, win_amt)
                        record(data, str(p2), "dice", stake, False, 0)
                    elif winner_id == p2:
                        add_bal(data, str(p2), win_amt)
                        record(data, str(p2), "dice", stake, True, win_amt)
                        record(data, str(p1), "dice", stake, False, 0)
                data.get("dice_live", {}).pop(mid, None)
                save(data)
                B = InlineKeyboardButton
                kb = InlineKeyboardMarkup([[
                    B("🔄 Play Again", callback_data=f"dg_again_{stake:.0f}"),
                    B("🔄 Double", callback_data=f"dg_double_{stake:.0f}"),
                ]])
                await update.message.reply_text(
                    f"🏆 <b>Game over!</b>\n\n"
                    f"Score:\n{n1} · {my_match['s1']}\n{n2} · {my_match['s2']}\n\n"
                    f"🎉 Congratulations, <b>{wname}</b>! You won <b>₹{win_amt:.2f}</b>!",
                    parse_mode="HTML",
                    reply_markup=kb,
                )
                return
            # next turn
            if my_match.get("vs_bot"):
                my_match["turn"] = p1
            else:
                # alternate: if just finished a full exchange, p1 starts next point or loser... DiceGamble continues alternate turns within point then next
                my_match["turn"] = p1 if not is_p1 else p2
                # after point resolved, start with p1 again like many bots
                my_match["turn"] = p1
            next_name = my_match["n1"] if my_match["turn"] == p1 else my_match["n2"]
            data["dice_live"][mid] = my_match
            save(data)
            await update.message.reply_text(
                f"🎲 <b>{next_name}</b>, your turn! Send 🎲",
                parse_mode="HTML",
            )
            return
        # waiting for opponent roll (PvP)
        if not my_match.get("vs_bot"):
            other = p2 if is_p1 else p1
            my_match["turn"] = other
            data["dice_live"][mid] = my_match
            save(data)
            oname = my_match["n2"] if is_p1 else my_match["n1"]
            await update.message.reply_text(
                f"🎲 <b>{oname}</b>, your turn! Send 🎲",
                parse_mode="HTML",
            )
        return

    if not is_target_group(update):
        return

    pending = data.get("pending_bets", {}).get(uid)
    if pending and pending.get("vs") == "bot":
        need_e = pending.get("emoji") or GAMES.get(pending.get("game", "dice"), ("🎲",))[0]
        got_e = getattr(getattr(update.message, "dice", None), "emoji", None)
        if got_e is None:
            return
        if got_e != need_e:
            try:
                await update.message.reply_text(
                    f"⚠️ This is *{pending.get('label', 'game')}* — send {need_e} not {got_e}",
                    parse_mode="Markdown",
                )
            except Exception:
                pass
            return
        if time.time() - float(pending.get("time", 0)) > PENDING_TIMEOUT:
            # refund
            add_bal(data, uid, float(pending.get("stake", 0)))
            data["pending_bets"].pop(uid, None)
            save(data)
            await update.message.reply_text("⏱️ Bet timed out — stake refunded.")
            return
        value = int(update.message.dice.value)
        rounds = int(pending.get("rounds") or 1)
        need = int(pending.get("need") or 1)
        rule = pending.get("rule", "normal")
        stake = float(pending.get("stake", 0))
        label = pending.get("label") or "Game"
        bid = pending.get("bet_id")
        emoji = need_e

        # Collect ALL user rolls first, then bot rolls
        uvals = pending.setdefault("user_vals", [])
        uvals.append(value)
        pending["user_vals"] = uvals
        pending["time"] = time.time()
        save(data)
        if len(uvals) < rounds:
            try:
                await update.message.reply_text(
                    f"<b>{emoji} Progress</b>\n\n"
                    f"<blockquote>Got it · {len(uvals)}/{rounds}\n"
                    f"Send {emoji} ×{rounds - len(uvals)} more</blockquote>",
                    parse_mode="HTML",
                )
            except Exception:
                pass
            return

        # lock: prevent double-settle if two dice arrive together
        if pending.get("settling"):
            return
        pending["settling"] = True
        data.setdefault("pending_bets", {})[uid] = pending
        save(data)

        # --- settle (must always reply) ---
        try:
            lo, hi = emoji_value_range(emoji)
            bot_vals = []
            for index in range(rounds):
                try:
                    bot_roll = await context.bot.send_dice(
                        chat_id=update.effective_chat.id,
                        emoji=emoji,
                    )
                    bot_vals.append(int(bot_roll.dice.value))
                    if index < rounds - 1:
                        await asyncio.sleep(3.2)
                except Exception as roll_error:
                    logger.warning("Telegram bot dice failed; using independent secure roll: %s", roll_error)
                    span = max(1, hi - lo + 1)
                    bot_vals.extend(lo + secrets.randbelow(span) for _ in range(rounds - len(bot_vals)))
                    break

            u_total = sum(int(x) for x in uvals)
            b_total = sum(int(x) for x in bot_vals)
            u_expr = "+".join(str(int(x)) for x in uvals) + f"={u_total}"
            b_expr = "+".join(str(int(x)) for x in bot_vals) + f"={b_total}"
            who = total_winner(u_total, b_total, rule)
            uname = user.username or user.first_name or "Player"
            rule_txt = "lowest total wins" if str(rule).lower() == "crazy" else "highest total wins"
            gkey = pending.get("game", "dice")

            # TIE → do NOT end match, re-roll same stake (all games: dice/dart/bowl/basket/football/slot)
            if who == "tie":
                # CRITICAL: clear settling so next throw is accepted
                pending["user_vals"] = []
                pending["settling"] = False
                pending.pop("settling", None)
                pending["time"] = time.time()
                data.setdefault("pending_bets", {})[uid] = pending
                save(data)
                body_html = (
                    f"<b>Round result — #{bid}</b>\n\n"
                    f"<blockquote>🤖 Bot threw {b_expr}\n"
                    f"👤 {uname} threw {u_expr}</blockquote>\n\n"
                    f"🤝 <b>TIE</b> — throw again.\n"
                    f"Send {emoji} again ×{rounds} to continue (stake still locked)."
                )
                try:
                    await update.message.reply_text(body_html, parse_mode="HTML")
                except Exception:
                    try:
                        await update.message.reply_text(f"TIE — throw again. Bot {b_expr} | You {u_expr}")
                    except Exception:
                        pass
                return

            win = who == "user"
            payout = round(stake * 1.85, 2) if win else 0.0
            if win:
                add_bal(data, uid, payout)
            try:
                record(data, user.id, f"{rule.title()} {label}", stake, win, payout if win else 0)
            except Exception:
                pass
            data.get("pending_bets", {}).pop(uid, None)
            try:
                data["jackpot_pool"] = round(float(data.get("jackpot_pool", 0) or 0) + stake * 0.02, 2)
            except Exception:
                pass
            save(data)
            bal_after = float(data.get("users", {}).get(uid, {}).get("balance", 0) or 0)

            # BlockVerse-style: blockquote = colored box on Telegram clients
            score_line = f"Score {u_total}-{b_total}" if rounds <= 1 else f"Totals {u_expr} vs {b_expr}"
            if win:
                body = (
                    f"<b>Round result — #{bid}</b>\n\n"
                    f"<blockquote>🤖 Bot threw {b_expr}\n"
                    f"👤 {uname} threw {u_expr}</blockquote>\n\n"
                    f"✅ <b>{uname} wins!</b> · +₹{payout - stake:.0f}\n"
                    f"💰 Balance: ₹{bal_after:.0f}"
                )
            else:
                body = (
                    f"<b>Round result — #{bid}</b>\n\n"
                    f"<blockquote>🤖 Bot threw {b_expr}\n"
                    f"👤 {uname} threw {u_expr}</blockquote>\n\n"
                    f"❌ <b>Bot Wins!</b> · Lost ₹{stake:.0f}\n"
                    f"💰 Balance: ₹{bal_after:.0f}"
                )
            kb = InlineKeyboardMarkup([[
                style_btn(f"🔄 Bet Again {int(stake)}", style="success",
                          callback_data=f"betagain_{gkey}_{int(stake)}_{rule}_{rounds}"),
            ]])
            try:
                await update.message.reply_text(body, reply_markup=kb, parse_mode="HTML")
            except Exception as e:
                logger.warning("result send %s", e)
                try:
                    await context.bot.send_message(update.effective_chat.id, body, reply_markup=kb, parse_mode="HTML")
                except Exception:
                    try:
                        await update.message.reply_text(body.replace("<blockquote>", "").replace("</blockquote>", "").replace("<b>", "").replace("</b>", ""), reply_markup=kb)
                    except Exception:
                        pass
        except Exception as e:
            logger.exception("settle fail %s", e)
            # emergency: clear pending + refund so user not stuck
            try:
                data = load()
                p = data.get("pending_bets", {}).pop(uid, None)
                if p:
                    add_bal(data, uid, float(p.get("stake", 0) or 0))
                save(data)
                await update.message.reply_text(
                    "⚠️ Game error — stake refunded. Try again."
                )
            except Exception:
                pass
        return


    # PvP — multi-roll total points, always show result
    for pid, ch in list(data.get("pvp", {}).items()):
        if ch.get("status") != "wait_emoji":
            continue
        if user.id not in (ch.get("a"), ch.get("b")):
            continue
        need_e = ch.get("emoji", "🎲")
        # Must be accepted 2-player match
        if not ch.get("b") or not ch.get("locked"):
            return
        if emoji != need_e:
            try:
                await update.message.reply_text(f"⚠️ This match needs {need_e} — you sent {emoji}")
            except Exception:
                pass
            return
        try:
            rounds = max(1, int(ch.get("rounds") or 1))
            a_id, b_id = str(ch["a"]), str(ch["b"])
            is_a = user.id == ch["a"]
            key = "a_vals" if is_a else "b_vals"
            vals = list(ch.get(key) or [])
            # also migrate old single-val fields
            if not vals and ch.get("a_val" if is_a else "b_val") is not None:
                vals = [int(ch.get("a_val" if is_a else "b_val"))]
            if len(vals) >= rounds:
                try:
                    await update.message.reply_text("Already finished your rolls.")
                except Exception:
                    pass
                return
            vals.append(int(value))
            ch[key] = vals
            # clear legacy
            ch["a_val"] = None
            ch["b_val"] = None
            ch["time"] = time.time()
            save(data)

            a_vals = list(ch.get("a_vals") or [])
            b_vals = list(ch.get("b_vals") or [])
            if len(a_vals) < rounds or len(b_vals) < rounds:
                left_a = rounds - len(a_vals)
                left_b = rounds - len(b_vals)
                await update.message.reply_text(
                    f"✅ Recorded {len(vals)}/{rounds} for you.\n"
                    f"Waiting: A {len(a_vals)}/{rounds} · B {len(b_vals)}/{rounds}"
                )
                return

            # both complete — settle by TOTAL points
            stake = float(ch.get("stake") or 0)
            rule = (ch.get("rule") or "normal").lower()
            a_total = sum(int(x) for x in a_vals)
            b_total = sum(int(x) for x in b_vals)
            a_expr = "+".join(str(int(x)) for x in a_vals) + f"={a_total}"
            b_expr = "+".join(str(int(x)) for x in b_vals) + f"={b_total}"
            if a_total == b_total:
                ch["a_vals"] = []
                ch["b_vals"] = []
                ch["time"] = time.time()
                data.setdefault("pvp", {})[pid] = ch
                save(data)
                await update.message.reply_text(
                    f"⚔️ PvP TIE\n"
                    f"A threw {a_expr}\n"
                    f"B threw {b_expr}\n\n"
                    f"🤝 No winner — both send {need_e} ×{rounds} again.\n"
                    f"(Stake still locked)"
                )
                return
            a_wins = (a_total > b_total) if rule == "normal" else (a_total < b_total)
            pot = stake * 2
            tax = pot * float(data.get("settings", {}).get("house_tax", 0.04) if False else 0.04)
            # HOUSE_TAX global
            try:
                tax = pot * HOUSE_TAX
            except Exception:
                tax = pot * 0.04
            win_amt = round(pot - tax, 2)
            winner = a_id if a_wins else b_id
            loser = b_id if a_wins else a_id
            add_bal(data, winner, win_amt)
            try:
                record(data, int(winner), f"PvP {ch.get('label','Game')}", stake, True, win_amt)
                record(data, int(loser), f"PvP {ch.get('label','Game')}", stake, False, 0)
            except Exception:
                pass
            data.get("pvp", {}).pop(pid, None)
            save(data)
            # names
            try:
                an = data.get("users", {}).get(a_id, {}).get("username") or a_id
                bn = data.get("users", {}).get(b_id, {}).get("username") or b_id
            except Exception:
                an, bn = a_id, b_id
            wname = an if a_wins else bn
            body = (
                f"⚔️ PvP Result — #{pid}\n\n"
                f"👤 {an} threw {a_expr}\n"
                f"👤 {bn} threw {b_expr}\n\n"
                f"{'📈 Highest total wins' if rule=='normal' else '⚡ Lowest total wins'}\n"
                f"🏆 {wname} wins ₹{win_amt:.0f}!"
            )
            await update.message.reply_text(body)
        except Exception as e:
            logger.exception("pvp settle %s", e)
            try:
                await update.message.reply_text("⚠️ PvP error — contact admin with match id.")
            except Exception:
                pass
        return



async def text_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return
    data = load()
    user = update.effective_user
    uid = str(user.id)
    msg = update.message.text.strip()
    # Owner natural language: "fix bot" / "bot fix" → maintenance heal
    if is_owner(data, user.id) and msg.lower().replace("!", "").strip() in (
        "fix bot", "bot fix", "fix the bot", "repair bot", "maintenance",
    ):
        context.args = []
        await cmd_fixbot(update, context)
        return
    # deposit amount step (DM) — UPI or CC
    dep = data.get("pending_dep_step", {}).get(uid)
    if dep and update.effective_chat.type == "private" and dep.get("step") == "amount":
        try:
            amt = float(msg.replace(",", ""))
        except Exception:
            await update.message.reply_text("⚠️ Sirf number. Example: `100`", parse_mode="Markdown")
            return
        if amt < min_dep_val(data):
            await update.message.reply_text(f"⚠️ Min deposit ₹{min_dep_val(data):.0f}")
            return
        method = (dep.get("method") or "upi").lower()
        suffix = secrets.randbelow(90) + 10  # 10-99
        unique_amt = round(int(amt) + suffix / 100.0, 2)
        data["pending_dep_step"][uid] = {
            "step": "ss",
            "amount": amt,
            "unique_amt": unique_amt,
            "method": method,
            "created": time.time(),
        }
        if method == "upi":
            data.setdefault("upi_unique", {})[f"{unique_amt:.2f}"] = {
                "uid": uid,
                "amount": amt,
                "unique_amt": unique_amt,
                "time": time.time(),
                "status": "waiting",
            }
        save(data)
        log_deposit(uid, method, amt, f"unique={unique_amt}")
        if method in ("cc", "cctip"):
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("🤖 Open @cctip_bot", url="https://t.me/cctip_bot")],
                [InlineKeyboardButton(f"💬 Support @{SUPPORT_PAY}", url=f"https://t.me/{SUPPORT_PAY}")],
                [InlineKeyboardButton("✅ Payment Done", callback_data="pay_done")],
            ])
            for oid in owners(data):
                try:
                    await context.bot.send_message(
                        oid,
                        f"🤖 <b>@cctip_bot DEPOSIT</b>\n"
                        f"User: <code>{uid}</code> @{update.effective_user.username or '-'}\n"
                        f"Amount: <b>₹{amt:.0f}</b>\n"
                        f"Ref: <code>CCTIP{uid[-6:]}{int(time.time())%10000}</code>\n"
                        f"User will tip via @cctip_bot → verify SS → "
                        f"<code>/addbal {uid} {int(amt)}</code>",
                        parse_mode="HTML",
                    )
                except Exception:
                    pass
            await update.message.reply_text(
                f"🤖 <b>HR CASINO · @cctip_bot</b>\n"
                f"<blockquote>"
                f"Amount: <b>₹{amt:.0f}</b>\n"
                f"Ref: <code>CCTIP{uid[-6:]}</code>\n\n"
                f"1. Open <b>@cctip_bot</b>\n"
                f"2. Send / tip <b>₹{amt:.0f}</b> to our account\n"
                f"3. Screenshot yahan bhejo\n"
                f"4. <b>Payment Done</b> dabao\n"
                f"5. Admin verify karke balance add karega\n"
                f"</blockquote>",
                parse_mode="HTML",
                reply_markup=kb,
            )
            return
        upi = data["settings"].get("upi", UPI_ID)
        name = data["settings"].get("upi_name", UPI_NAME)
        kb = InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ Payment Done", callback_data="pay_done")
        ]])
        await update.message.reply_text(
            f"💳 <b>UPI DEPOSIT</b>\n"
            f"<blockquote>"
            f"Pay exact amount:\n"
            f"<b>₹{unique_amt:.2f}</b>\n"
            f"(base ₹{amt:.0f} + auto ID)\n\n"
            f"UPI: <code>{upi}</code>\n"
            f"Name: {name}\n"
            f"</blockquote>\n"
            f"⚠️ Pay <b>exact ₹{unique_amt:.2f}</b> — then tap Payment Done\n"
            f"or send screenshot.\n"
            f"Owner auto-matches this unique amount.",
            parse_mode="HTML",
            reply_markup=kb,
        )
        from pathlib import Path as P
        candidates = []
        qf = data.get("settings", {}).get("qr_file")
        if qf:
            candidates.append(qf)
        candidates += ["upi_qr.jpg", "qr.jpg", "upi_qr.png", "qr.png"]
        for cand in candidates:
            if P(cand).exists():
                try:
                    await update.message.reply_photo(
                        photo=open(cand, "rb"),
                        caption=f"💎 QR · Pay exact ₹{unique_amt:.2f}\n{upi}",
                        reply_markup=kb,
                    )
                except Exception as e:
                    logger.warning("qr send %s", e)
                break
        return
    # withdraw steps (DM only)
    step = data.get("pending_wd_step", {}).get(uid)
    text = msg  # keep var name for rest of function
    if step and update.effective_chat.type == "private":
        if step.get("step") == "detail":
            # CWallet / cctip / crypto address
            step["detail"] = text
            step["upi"] = text  # reuse field for admin view
            step["step"] = "amount"
            data["pending_wd_step"][uid] = step
            save(data)
            await update.message.reply_text("💵 Ab *amount* send (number only):", parse_mode="Markdown")
            return
        if step.get("step") == "upi":
            step["upi"] = text
            step["method"] = step.get("method") or "upi"
            step["step"] = "amount"
            data["pending_wd_step"][uid] = step
            save(data)
            await update.message.reply_text("💵 Ab *amount* send (number only):", parse_mode="Markdown")
            return
        if step.get("step") == "amount":
            try:
                amt = float(text.replace(",", ""))
            except Exception:
                await update.message.reply_text("Sirf number. Example: 200")
                return
            u = ensure_user(data, user)
            min_wd = float(data.get("settings", {}).get("min_withdraw", MIN_WITHDRAW))
            if amt < min_wd:
                await update.message.reply_text(f"Min ₹{min_wd:.0f}")
                return
            if float(u.get("balance", 0)) < amt:
                await update.message.reply_text("Low balance")
                return
            take_bal(data, uid, amt)
            wid = rid("WD")
            method = step.get("method") or "upi"
            dest = step.get("upi") or step.get("detail") or "-"
            data.setdefault("pending_wd", {})[wid] = {
                "id": wid,
                "user_id": user.id,
                "username": user.username or "",
                "name": user.first_name or "",
                "upi": dest,
                "method": method,
                "amount": amt,
                "status": "pending",
                "time": time.time(),
            }
            data.get("pending_wd_step", {}).pop(uid, None)
            save(data)
            await update.message.reply_text(
                f"✅ Withdraw request *{wid}*\n"
                f"Method: `{method}`\n"
                f"To: `{dest}`\n"
                f"Amount: ₹{amt:.0f}\n"
                f"Admin approve karega.",
                parse_mode="Markdown",
            )
            kb = InlineKeyboardMarkup([[
                InlineKeyboardButton("✅ Pay Done", callback_data=f"wdok_{wid}"),
                InlineKeyboardButton("❌ Reject", callback_data=f"wdno_{wid}"),
            ]])
            for oid in owners(data):
                try:
                    await context.bot.send_message(
                        oid,
                        f"⬆️ *Withdraw request*\n"
                        f"ID: `{wid}`\n"
                        f"User: {user.id} @{user.username or '-'}\n"
                        f"Method: `{method}`\n"
                        f"To: `{dest}`\n"
                        f"Amount: *₹{amt:.0f}*",
                        parse_mode="Markdown",
                        reply_markup=kb,
                    )
                except Exception:
                    pass
            return


async def photo_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load()
    user = update.effective_user
    # Deposit SS DM only mein — group pe ignore / warn
    if is_group(update):
        await update.message.reply_text(
            "🔒 *Deposit only in bot DM*\n"
            "Group pe payment SS mat send.\n"
            "Bot ko personal message karo → screenshot + caption amount.",
            parse_mode="Markdown",
        )
        return
    ensure_user(data, user)
    # Prefer amount from deposit step; caption optional
    amount = None
    dep = data.get("pending_dep_step", {}).get(str(user.id))
    if dep and dep.get("amount"):
        amount = float(dep["amount"])
        data.get("pending_dep_step", {}).pop(str(user.id), None)
    if amount is None and update.message.caption:
        import re as _re
        m = _re.search(r"(\d+(?:\.\d+)?)", update.message.caption)
        if m:
            amount = float(m.group(1))
    pid = rid("P")
    photo = update.message.photo[-1]
    data.setdefault("pending_pay", {})[pid] = {
        "user_id": user.id,
        "amount": amount,  # may be None
        "photo_file_id": photo.file_id,
        "status": "pending",
        "time": datetime.now().isoformat(timespec="seconds"),
    }
    save(data)
    amt_txt = f"₹{amount:.0f}" if amount else "amount not in caption"
    await update.message.reply_text(
        f"✅ SS received `{pid}`\n{amt_txt}\nAdmin private check karega.",
        parse_mode="Markdown",
    )
    kb = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ 50", callback_data=f"appr_{pid}_50"),
            InlineKeyboardButton("✅ 100", callback_data=f"appr_{pid}_100"),
            InlineKeyboardButton("✅ 200", callback_data=f"appr_{pid}_200"),
        ],
        [
            InlineKeyboardButton("✅ 500", callback_data=f"appr_{pid}_500"),
            InlineKeyboardButton("✅ 1000", callback_data=f"appr_{pid}_1000"),
        ],
        [
            InlineKeyboardButton("✅ Use caption amt" if amount else "✅ Reply /addbal", callback_data=f"appr_{pid}_auto"),
            InlineKeyboardButton("❌ Reject", callback_data=f"rej_{pid}"),
        ],
    ])
    for tid in owners(data):
        try:
            await context.bot.send_photo(
                tid,
                photo=photo.file_id,
                caption=f"💳 Deposit SS\nID: {pid}\nUser: {user.id} @{user.username or '-'}\nCaption amt: {amt_txt}\nApprove amount button tap:",
                reply_markup=kb,
            )
        except Exception as e:
            logger.warning("owner ss fail %s %s", tid, e)



async def cmd_allow(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Owner: enable bot games in this group (multi-group support)."""
    data = load()
    if not is_owner(data, update.effective_user.id):
        await update.message.reply_text("⛔ Only owner can /allow groups.")
        return
    chat = update.effective_chat
    if not chat or chat.type not in ("group", "supergroup"):
        await update.message.reply_text("Run /allow inside a group.")
        return
    allowed = data.setdefault("allowed_groups", [])
    cid = int(chat.id)
    if cid not in [int(x) for x in allowed]:
        allowed.append(cid)
        save(data)
        try:
            await reply_prem(update.message, [("check",), f" Group *allowed*\n`{cid}`\nBot games ON here."])
        except Exception:
            await update.message.reply_text(f"✅ Group allowed `{cid}`", parse_mode="Markdown")
    else:
        await update.message.reply_text("Already allowed.")


async def cmd_disallow(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load()
    if not is_owner(data, update.effective_user.id):
        return
    chat = update.effective_chat
    if not chat:
        return
    allowed = data.setdefault("allowed_groups", [])
    cid = int(chat.id)
    data["allowed_groups"] = [x for x in allowed if int(x) != cid]
    save(data)
    await update.message.reply_text(f"❌ Group disallowed (`{cid}`).", parse_mode="Markdown")


async def cmd_allowlist(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load()
    if not is_owner(data, update.effective_user.id):
        return
    groups = data.get("allowed_groups") or []
    main = data.get("settings", {}).get("group_id") or GROUP_ID
    lines = [f"Main: `{main}`"] + [f"• `{g}`" for g in groups]
    await update.message.reply_text("Allowed groups:\n" + "\n".join(lines), parse_mode="Markdown")


# admin
async def cmd_addbal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load()
    if not is_owner(data, update.effective_user.id):
        await update.message.reply_text(
            f"❌ Owner only\nYour ID: `{update.effective_user.id}`\nOwners: `{list(owners(data))}`",
            parse_mode="Markdown",
        )
        return
    if update.message.reply_to_message and context.args:
        uid = str(update.message.reply_to_message.from_user.id)
        amt = float(context.args[0])
    elif len(context.args) >= 2:
        uid, amt = str(context.args[0]), float(context.args[1])
    else:
        await update.message.reply_text("`/addbal USER_ID 500` or reply + `/addbal 500`", parse_mode="Markdown")
        return
    add_bal(data, uid, amt)
    ref_pay = apply_referral_first_deposit(data, uid, amt)
    save(data)
    extra = f" · ref +₹{ref_pay:.0f}" if ref_pay else ""
    await update.message.reply_text(
        f"✅ +₹{amt:.0f} → `{uid}` = ₹{data['users'][uid]['balance']:.0f}{extra}",
        parse_mode="Markdown",
    )
    try:
        await context.bot.send_message(int(uid), f"💰 +₹{amt:.0f}")
    except Exception:
        pass
    if ref_pay:
        try:
            rid_ = data["users"][uid].get("referred_by")
            await context.bot.send_message(
                int(rid_),
                f"🎁 Referral: +₹{ref_pay:.0f} (₹10 + 20% of ₹{amt:.0f})",
            )
        except Exception:
            pass




async def cmd_setgroup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load()
    if not is_owner(data, update.effective_user.id):
        return
    if not context.args:
        await update.message.reply_text(
            f"Current group: `{data.get('settings', {}).get('group_id', GROUP_ID)}`\nUsage: /setgroup -100xxxxxxxxxx",
            parse_mode="Markdown",
        )
        return
    try:
        gid = int(context.args[0])
    except Exception:
        await update.message.reply_text("Invalid id")
        return
    data.setdefault("settings", {})["group_id"] = gid
    save(data)
    await update.message.reply_text(f"✅ Group set: `{gid}`", parse_mode="Markdown")


async def cmd_setgrouplink(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load()
    if not is_owner(data, update.effective_user.id):
        return
    if not context.args:
        await update.message.reply_text("Usage: /setgrouplink https://t.me/+xxxx")
        return
    data.setdefault("settings", {})["group_link"] = context.args[0]
    save(data)
    await update.message.reply_text(f"✅ Group link set:\n{context.args[0]}")

async def cmd_addowner(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load()
    if not is_owner(data, update.effective_user.id):
        await update.message.reply_text("👑 Owner only")
        return
    if not context.args:
        await update.message.reply_text("Usage: `/addowner 123456789`", parse_mode="Markdown")
        return
    try:
        oid = int(context.args[0])
    except Exception:
        await update.message.reply_text("Invalid user id")
        return
    lst = data.setdefault("settings", {}).setdefault("owners", [])
    if oid not in lst:
        lst.append(oid)
        save(data)
    await update.message.reply_text(f"✅ Owner added: `{oid}`", parse_mode="Markdown")


async def cmd_removeowner(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Remove a dynamically added owner (not hardcoded OWNER_IDS)."""
    data = load()
    if not is_owner(data, update.effective_user.id):
        await update.message.reply_text("👑 Owner only")
        return
    if not context.args:
        lst = data.get("settings", {}).get("owners", [])
        hard = sorted(OWNER_IDS)
        await update.message.reply_text(
            "Usage: `/removeowner 123456789`\n\n"
            f"Hardcoded (code se): `{hard}`\n"
            f"Extra owners: `{lst}`\n\n"
            "Note: Hardcoded OWNER_IDS code edit se hi hatenge.",
            parse_mode="Markdown",
        )
        return
    try:
        oid = int(context.args[0])
    except Exception:
        await update.message.reply_text("Invalid user id")
        return
    if oid in OWNER_IDS:
        await update.message.reply_text(
            f"⚠️ `{oid}` hardcoded OWNER_IDS mein hai.\n"
            "Isse code file se hatao, command se nahi.",
            parse_mode="Markdown",
        )
        return
    lst = data.setdefault("settings", {}).setdefault("owners", [])
    if oid in lst:
        data["settings"]["owners"] = [x for x in lst if int(x) != oid]
        save(data)
        await update.message.reply_text(f"✅ Owner removed: `{oid}`", parse_mode="Markdown")
    else:
        await update.message.reply_text(f"`{oid}` owner list mein nahi mila", parse_mode="Markdown")


ADMIN_GAMES = {
    "dice": ("🎲", "Dice"),
    "basket": ("🏀", "Basketball"),
    "football": ("⚽", "Football"),
    "bowl": ("🎳", "Bowling"),
    "dart": ("🎯", "Darts"),
    "slot": ("🎰", "Slots"),
    "coin": ("🪙", "Coin Flip"),
    "bj": ("🃏", "Blackjack"),
    "rps": ("✊", "Rock Paper Scissors"),
    "mines": ("💣", "Mines"),
    "limbo": ("📈", "Limbo"),
    "7up": ("🎲", "7 Up / 7 Down"),
    "dr": ("🎯", "Dice Roulette"),
}


def panel_keyboard(data):
    pending_deposits = sum(1 for p in (data.get("pending_pay") or {}).values() if p.get("status") == "pending")
    pending_withdrawals = sum(1 for p in (data.get("pending_wd") or {}).values() if p.get("status") == "pending")
    bot_action = "⏸ Pause bot" if bot_is_on(data) else "▶ Resume bot"
    bot_callback = "panel_pause" if bot_is_on(data) else "panel_resume"
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📊 Overview", callback_data="panel_home"),
         InlineKeyboardButton("🎮 Games", callback_data="panel_games")],
        [InlineKeyboardButton(f"⬇️ Deposits · {pending_deposits}", callback_data="panel_deposits"),
         InlineKeyboardButton(f"⬆️ Withdrawals · {pending_withdrawals}", callback_data="panel_withdrawals")],
        [InlineKeyboardButton(bot_action, callback_data=bot_callback),
         InlineKeyboardButton("📖 Admin help", callback_data="panel_commands")],
        [InlineKeyboardButton("🔄 Refresh", callback_data="panel_home"),
         InlineKeyboardButton("✖ Close", callback_data="panel_close")],
    ])


def panel_overview_parts(data):
    stats = data.get("stats", {})
    pending_deposits = sum(1 for p in (data.get("pending_pay") or {}).values() if p.get("status") == "pending")
    pending_withdrawals = sum(1 for p in (data.get("pending_wd") or {}).values() if p.get("status") == "pending")
    wagered = float(stats.get("wagered", 0) or 0)
    paid = float(stats.get("paid", 0) or 0)
    return [
        ("crown",), " OWNER DASHBOARD", chr(10), chr(10),
        ("user",), f" Players: {len(data.get('users', {}))}", chr(10),
        ("dice",), f" Completed bets: {int(stats.get('bets', 0) or 0)}", chr(10),
        ("money",), f" Total wagered: ₹{wagered:.2f}", chr(10),
        ("cash",), f" Game payouts: ₹{paid:.2f}", chr(10),
        ("chart",), f" Wagered minus payouts: ₹{wagered - paid:.2f}", chr(10),
        ("gift",), f" Jackpot pool: ₹{float(data.get('jackpot_pool', 0) or 0):.2f}", chr(10),
        ("alert",), f" Pending deposits: {pending_deposits} · withdrawals: {pending_withdrawals}", chr(10),
        ("check",), " Bot: " + ("Running" if bot_is_on(data) else "Paused"), chr(10), chr(10),
        "Net figure excludes deposits, withdrawals, bonuses, and other wallet adjustments.",
    ]


async def cmd_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load()
    if not is_owner(data, update.effective_user.id):
        await update.message.reply_text("Owner only.")
        return
    await reply_prem(update.message, panel_overview_parts(data), reply_markup=panel_keyboard(data))



async def cmd_support(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Single support contact — @Hrcasinosupport"""
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("💬 @Hrcasinosupport", url="https://t.me/Hrcasinosupport")],
    ])
    text = (
        "🛡 <b>CUSTOMER SUPPORT</b>\n\n"
        "All help (deposit / withdraw / games):\n"
        "<b>@Hrcasinosupport</b>\n\n"
        "Send:\n"
        "• Username\n• User ID\n• Issue\n• TX ID (if any)\n• Screenshot"
    )
    await update.message.reply_text(text, parse_mode="HTML", reply_markup=kb)


async def cmd_admincommands(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Button panel like /start — all admin tools."""
    data = load()
    uid = update.effective_user.id
    if not is_owner(data, uid) and uid not in set(data.get("bot_admins") or []):
        await update.message.reply_text("👑 Owner / Admin only")
        return
    B = InlineKeyboardButton
    kb = InlineKeyboardMarkup([
        [B("➕ Add Bal", callback_data="adm_help_addbal"),
         B("➖ Cut Bal", callback_data="adm_help_cutbal")],
        [B("❄️ Freeze", callback_data="adm_help_freeze"),
         B("🔥 Unfreeze", callback_data="adm_help_unfreeze")],
        [B("⚙️ Limits", callback_data="adm_run_setlimits"),
         B("🎰 Rig mode", callback_data="adm_help_rig")],
        [B("💰 Credit UPI", callback_data="adm_help_credit"),
         B("📈 Max bet", callback_data="adm_help_maxbet")],
        [B("📉 Min bet", callback_data="adm_help_minbet"),
         B("🏦 HB / HBadd", callback_data="adm_help_hb")],
        [B("✅ Bot ON", callback_data="adm_run_boton"),
         B("🛠 Bot OFF", callback_data="adm_run_botoff")],
        [B("📢 Announce", callback_data="adm_help_announce"),
         B("📋 Panel", callback_data="adm_run_panel")],
        [B("🔗 Set wins ch", callback_data="adm_help_winsch"),
         B("📜 Logs", callback_data="adm_run_logs")],
        [B("🏠 Close", callback_data="adm_close")],
    ])
    await update.message.reply_text(
        "👑 <b>Admin Help</b>\n\n"
        "Tap a button for usage or quick action.\n"
        "Sensitive cmds (addbal etc.) show the command format.",
        parse_mode="HTML",
        reply_markup=kb,
    )



async def cmd_setupiandqr(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await cmd_setupi(update, context)


async def cmd_setupi(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Set UPI + QR.
    - /setupi upi@id
    - /setupi upi@id Name
    - Reply to QR photo: /setupiandqr
    - Reply to photo+caption with UPI text: /setupiandqr
    - Reply to text containing UPI: /setupi
    """
    data = load()
    if not is_owner(data, update.effective_user.id):
        await update.message.reply_text("Owner only. Use /myid first.")
        return
    msg = update.message
    reply = msg.reply_to_message
    saved = []

    # UPI from command args
    if context.args:
        upi = context.args[0].strip()
        data.setdefault("settings", {})["upi"] = upi
        if len(context.args) > 1:
            data["settings"]["upi_name"] = " ".join(context.args[1:])
        save(data)
        saved.append(f"UPI: {upi}")

    # UPI from reply text / caption
    if reply:
        blob = " ".join(filter(None, [
            reply.caption or "",
            reply.text or "",
        ]))
        # find email-like upi
        import re as _re
        m = _re.search(r"[\w.\-]+@[\w.\-]+", blob)
        if m and not context.args:
            upi = m.group(0)
            data.setdefault("settings", {})["upi"] = upi
            save(data)
            saved.append(f"UPI: {upi}")
        # any other line as name?
        if "upi_name" not in data.get("settings", {}) and blob:
            for line in blob.splitlines():
                line = line.strip()
                if line and "@" not in line and len(line) < 40:
                    data.setdefault("settings", {})["upi_name"] = line
                    save(data)
                    saved.append(f"Name: {line}")
                    break

    # QR from reply photo
    if reply and reply.photo:
        photo = reply.photo[-1]
        try:
            tg_file = await context.bot.get_file(photo.file_id)
            out = "upi_qr.jpg"
            try:
                await tg_file.download_to_drive(custom_path=out)
            except TypeError:
                await tg_file.download_to_drive(out)
            except Exception:
                # fallback write bytes
                bio = await tg_file.download_as_bytearray()
                with open(out, "wb") as f:
                    f.write(bio)
            data.setdefault("settings", {})["qr_file"] = out
            save(data)
            saved.append("QR saved (upi_qr.jpg)")
        except Exception as e:
            await update.message.reply_text(f"QR save fail: {e}")
            return

    if saved:
        upi = data.get("settings", {}).get("upi", UPI_ID)
        name = data.get("settings", {}).get("upi_name", UPI_NAME)
        await update.message.reply_text(
            "✅ Payment setup done\n"
            + "\n".join(f"• {s}" for s in saved)
            + f"\n\nCurrent:\nUPI: {upi}\nName: {name}\nQR: {'yes' if Path('upi_qr.jpg').exists() else 'no'}"
        )
    else:
        await update.message.reply_text(
            "Usage:\n"
            "/setupi yourupi@oksbi\n"
            "/setupi yourupi@oksbi YourName\n\n"
            "QR + UPI:\n"
            "1) Photo (QR) send, caption mein UPI likho\n"
            "2) Uspe reply karke /setupiandqr"
        )



async def cmd_stats(update, context):
    data = load()
    if is_owner(data, update.effective_user.id):
        await update.message.reply_text(str(data.get("stats")))


async def cmd_ban(update, context):
    data = load()
    if is_owner(data, update.effective_user.id) and context.args:
        data.setdefault("banned", []).append(context.args[0])
        save(data)
        await update.message.reply_text("Banned")


async def cmd_unban(update, context):
    data = load()
    if is_owner(data, update.effective_user.id) and context.args:
        data["banned"] = [x for x in data.get("banned", []) if x != context.args[0]]
        save(data)
        await update.message.reply_text("Unbanned")


async def cmd_on(update, context):
    data = load()
    if is_owner(data, update.effective_user.id):
        data["settings"]["bot_on"] = True
        save(data)
        await update.message.reply_text("ON")


async def cmd_off(update, context):
    data = load()
    if is_owner(data, update.effective_user.id):
        data["settings"]["bot_on"] = False
        save(data)
        await update.message.reply_text("OFF")


# ========== AXOM-STYLE ADDONS ==========

def user_currency(data, uid) -> str:
    u = data.get("users", {}).get(str(uid)) or {}
    return (u.get("currency") or "INR").upper()


def fmt_money(data, uid, amount_inr: float) -> str:
    cur = user_currency(data, uid)
    rates = data.get("settings", {}).get("rates") or DEFAULT_RATES
    rate = float(rates.get(cur, 1) or 1)
    if cur == "INR" or rate <= 0:
        return f"₹{amount_inr:.2f}"
    val = amount_inr / rate
    return f"{val:.2f} {cur}"


async def cmd_currency(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load()
    user = update.effective_user
    ensure_user(data, user)
    cur = user_currency(data, user.id)
    rows = []
    row = []
    for i, c in enumerate(CURRENCIES):
        label = f"✅ {c}" if c == cur else c
        st = "success" if c == cur else "primary"
        row.append(style_btn(label, style=st, callback_data=f"setcur_{c}"))
        if len(row) == 3:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    await update.message.reply_text(
        "🌍 <b>Select display currency</b>\n"
        "INR is base for gameplay; this controls how values are shown.",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(rows),
    )


async def cmd_freeze(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Owner: /freeze 123456 or reply /freeze — freeze wallet"""
    data = load()
    if not is_owner(data, update.effective_user.id):
        return
    tid = None
    if context.args:
        a = context.args[0].replace("@", "")
        if a.isdigit():
            tid = int(a)
        else:
            # search username
            for uid, u in data.get("users", {}).items():
                if (u.get("username") or "").lower() == a.lower():
                    tid = int(uid)
                    break
    elif update.message.reply_to_message:
        tid = update.message.reply_to_message.from_user.id
    if not tid:
        await update.message.reply_text("Usage: /freeze USER_ID or reply to user")
        return
    data.setdefault("frozen", {})[str(tid)] = {"by": update.effective_user.id, "time": time.time()}
    save(data)
    await update.message.reply_text(f"🔒 Frozen user `{tid}` — cannot play until /unfreeze", parse_mode="Markdown")


async def cmd_unfreeze(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load()
    if not is_owner(data, update.effective_user.id):
        return
    tid = None
    if context.args and context.args[0].replace("@", "").isdigit():
        tid = int(context.args[0].replace("@", ""))
    elif update.message.reply_to_message:
        tid = update.message.reply_to_message.from_user.id
    if not tid:
        await update.message.reply_text("Usage: /unfreeze USER_ID")
        return
    data.get("frozen", {}).pop(str(tid), None)
    save(data)
    await update.message.reply_text(f"🔓 Unfrozen `{tid}`", parse_mode="Markdown")


async def cmd_setlimits(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Owner panel for min/max bet & withdraw"""
    data = load()
    if not is_owner(data, update.effective_user.id):
        return
    s = data["settings"]
    kb = InlineKeyboardMarkup([
        [style_btn(f"Min bet ₹{s.get('min_bet', MIN_BET)}", style="primary", callback_data="lim_info")],
        [
            style_btn("MinBet 10", style="success", callback_data="setlim_minbet_10"),
            style_btn("MinBet 50", style="success", callback_data="setlim_minbet_50"),
            style_btn("MinBet 300", style="success", callback_data="setlim_minbet_300"),
        ],
        [
            style_btn("MaxBet 300", style="primary", callback_data="setlim_maxbet_300"),
            style_btn("MaxBet 1000", style="primary", callback_data="setlim_maxbet_1000"),
            style_btn("MaxBet 5000", style="primary", callback_data="setlim_maxbet_5000"),
        ],
        [
            style_btn("MinWD 150", style="success", callback_data="setlim_minwd_150"),
            style_btn("MinWD 300", style="success", callback_data="setlim_minwd_300"),
        ],
        [
            style_btn("MaxWD 5k", style="primary", callback_data="setlim_maxwd_5000"),
            style_btn("MaxWD 25k", style="primary", callback_data="setlim_maxwd_25000"),
            style_btn("MaxWD 50k", style="primary", callback_data="setlim_maxwd_50000"),
        ],
        [
            style_btn("Rig OFF", style="success", callback_data="setrig_off"),
            style_btn("Rig 60%", style="primary", callback_data="setrig_active"),
            style_btn("Rig 75%", style="danger", callback_data="setrig_full"),
        ],
    ])
    await update.message.reply_text(
        f"⚙️ <b>Limits & Rig</b>\n"
        f"Min bet: ₹{s.get('min_bet')} · Max bet: ₹{s.get('max_bet')}\n"
        f"Min WD: ₹{s.get('min_withdraw', MIN_WITHDRAW)} · Max WD: ₹{s.get('max_withdraw', 50000)}\n"
        f"Rig: <b>{s.get('rig_mode', 'off')}</b>",
        parse_mode="HTML",
        reply_markup=kb,
    )


async def cmd_loyalty(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load()
    user = update.effective_user
    u = ensure_user(data, user)
    loy = u.setdefault("loyalty", {
        "pts": 0, "lifetime": 0, "streak": 0, "last_login": "",
        "daily": False, "wager_pts": 0, "games_today": [], "win_streak": 0,
    })
    today = date.today().isoformat()
    if loy.get("last_login") != today:
        # new day reset daily flags
        if loy.get("last_login"):
            try:
                prev = date.fromisoformat(loy["last_login"])
                if (date.today() - prev).days == 1:
                    loy["streak"] = int(loy.get("streak", 0)) + 1
                else:
                    loy["streak"] = 1
            except Exception:
                loy["streak"] = 1
        else:
            loy["streak"] = 1
        loy["last_login"] = today
        loy["daily"] = False
        loy["wager_pts"] = 0
        loy["games_today"] = []
        # auto claim daily login pts
        loy["pts"] = int(loy.get("pts", 0)) + 10
        loy["lifetime"] = int(loy.get("lifetime", 0)) + 10
        loy["daily"] = True
        save(data)
    pts = int(loy.get("pts", 0))
    life = int(loy.get("lifetime", 0))
    streak = int(loy.get("streak", 0))
    games = len(loy.get("games_today") or [])
    text = (
        f"💎 <b>LOYALTY BONUS</b>\n"
        f"<blockquote>"
        f"<b>{pts} PTS</b>\n"
        f"Lifetime: {life} pts · Streak: {streak} days\n\n"
        f"📅 Daily Login: {'claimed' if loy.get('daily') else 'pending'}\n"
        f"💰 Wager pts: {loy.get('wager_pts', 0)}/50\n"
        f"🎮 Unique games today: {games}/5\n"
        f"🔥 Win streak: {loy.get('win_streak', 0)}/5\n"
        f"</blockquote>\n"
        f"Earn: Deposit 2pts/$1 · Refer 25 · Level-up 50\n"
        f"Redeem: /redeem POINTS"
    )
    kb = InlineKeyboardMarkup([[
        style_btn("💎 Redeem Points", style="primary", callback_data="loyalty_redeem"),
        style_btn("📊 History", style="primary", callback_data="menu_history"),
    ]])
    await update.message.reply_text(text, parse_mode="HTML", reply_markup=kb)


async def cmd_redeem(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load()
    user = update.effective_user
    u = ensure_user(data, user)
    loy = u.setdefault("loyalty", {"pts": 0})
    if not context.args:
        await update.message.reply_text("Usage: /redeem 100  (100 pts = ₹10)")
        return
    try:
        pts = int(context.args[0])
    except Exception:
        await update.message.reply_text("Number only")
        return
    if pts < 50:
        await update.message.reply_text("Min redeem 50 pts")
        return
    if int(loy.get("pts", 0)) < pts:
        await update.message.reply_text(f"Not enough pts ({loy.get('pts', 0)})")
        return
    loy["pts"] = int(loy.get("pts", 0)) - pts
    credit = pts / 10.0  # 10 pts = ₹1
    add_bal(data, str(user.id), credit)
    save(data)
    await update.message.reply_text(f"✅ Redeemed {pts} pts → +₹{credit:.0f}")


async def cmd_crypto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show deposit crypto addresses"""
    lines = ["🟡 <b>Crypto deposit addresses</b>\n"]
    for k, v in CRYPTO_WALLETS.items():
        lines.append(f"<b>{k}</b>\n<code>{v}</code>\n")
    lines.append("\nAfter TX, send hash to @" + SUPPORT_PAY)
    await update.message.reply_text("\n".join(lines), parse_mode="HTML")


async def cmd_crossyroad(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Chicken Road / Crossy Road — DiceGamble style card + buttons."""
    msg = update.effective_message
    if not msg:
        return
    B = InlineKeyboardButton
    kb = InlineKeyboardMarkup([
        [B("🐔 Play Chicken Road", callback_data="mini_crossy_play")],
        [B("📖 Rules", callback_data="mini_crossy_rules")],
    ])
    text = (
        "🐔 <b>Play Chicken Road</b>\n\n"
        "Hop across the road, dodge cars &amp; trucks, "
        "collect coins and reach the <b>GOAL</b>.\n\n"
        "Press the button below to start!\n\n"
        "<b>Examples:</b>\n"
        "<code>/crossy 50</code> — bet ₹50\n"
        "<code>/crossy half</code> — half balance\n"
        "<code>/crossy all</code> — all-in"
    )
    await msg.reply_text(text, parse_mode="HTML", reply_markup=kb)


async def cmd_wheel_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    if not msg:
        return
    B = InlineKeyboardButton
    kb = InlineKeyboardMarkup([
        [B("✅ Play", callback_data="mini_wheel_play"),
         B("📖 Rules", callback_data="mini_wheel_rules")],
    ])
    await msg.reply_text(
        "🎡 <b>Wheel</b>\n\n"
        "Classic wheel of fortune — spin and collect multipliers.\n\n"
        "Quick start: <code>/wheel 50</code>\n"
        "<code>/wheel half</code> · <code>/wheel all</code>",
        parse_mode="HTML",
        reply_markup=kb,
    )


async def cmd_tower(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Monkey Tower — climb floors, cash out or risk higher.
    /tower 50 · /tower half · /tower all
    """
    data = load()
    user = update.effective_user
    msg = update.effective_message
    if not msg:
        return
    if not await check_bot_and_game(update, context, data, "tower"):
        return
    args = list(context.args or [])
    if not args:
        B = InlineKeyboardButton
        await msg.reply_text(
            "🐵 <b>Monkey Tower</b>\n\n"
            "Climb floors · each floor multiplies.\n"
            "Cash out anytime or risk the next floor.\n\n"
            "<code>/tower 50</code> · <code>/tower half</code> · <code>/tower all</code>",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [B("🐵 Play ₹50", callback_data="tower_start_50")],
                [B("📖 Rules", callback_data="mini_tower_rules")],
            ]),
        )
        return
    u = ensure_user(data, user)
    bal = float(u.get("balance", 0) or 0)
    a0 = args[0].lower()
    if a0 in ("half", "1/2"):
        stake = round(bal / 2, 2)
    elif a0 in ("all", "allin", "all-in"):
        stake = round(bal, 2)
    else:
        try:
            stake = float(a0.replace(",", ""))
        except Exception:
            await msg.reply_text("Example: /tower 50")
            return
    mn = min_bet_val(data)
    mx = float(data.get("settings", {}).get("max_bet", MAX_BET))
    if stake < mn or stake > mx:
        await msg.reply_text(f"Stake ₹{mn:.0f}–₹{mx:.0f}")
        return
    if bal < stake or not take_bal(data, str(user.id), stake):
        await msg.reply_text("Low balance!")
        return
    # start tower session
    data.setdefault("tower_games", {})[str(user.id)] = {
        "stake": stake,
        "floor": 0,
        "mult": 1.0,
        "alive": True,
        "time": time.time(),
    }
    save(data)
    await _tower_show(msg, user.id, stake, 0, 1.0)


async def _tower_show(msg, uid, stake, floor, mult):
    pot = round(stake * mult, 2)
    B = InlineKeyboardButton
    kb = InlineKeyboardMarkup([
        [B("🍌 Climb next floor", callback_data=f"tower_climb_{uid}")],
        [B(f"💰 Cash out ₹{pot:.2f}", callback_data=f"tower_cash_{uid}")],
    ])
    await msg.reply_text(
        f"🐵 <b>Monkey Tower</b>\n\n"
        f"Floor: <b>{floor}</b>\n"
        f"Multiplier: <b>{mult:.2f}x</b>\n"
        f"Stake: ₹{stake:.2f} · Pot: ₹{pot:.2f}\n\n"
        f"Climb for higher mult — or cash out now.",
        parse_mode="HTML",
        reply_markup=kb,
    )


async def cmd_roulette(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Roulette: Telegram 🎰 dice FIRST → result MUST match dice.value.
    /roulette 50 red · /roul 20 black · /roulette 50 17
    """
    user = update.effective_user
    msg = update.effective_message
    data = load()
    args = [a.lower().strip() for a in (context.args or [])]
    if len(args) < 2:
        B = InlineKeyboardButton
        kb = InlineKeyboardMarkup([
            [B("✅ Play", callback_data="mini_roulette_play"),
             B("📖 Rules", callback_data="mini_roulette_rules")],
        ])
        await msg.reply_text(
            "🎡 <b>Roulette</b>\n\n"
            "Bot pehle 🎰 fekega — <b>usi emoji ka result</b> win/lose decide karega.\n\n"
            "<code>/roulette 50 red</code> · 1.95×\n"
            "<code>/roulette 50 black</code> · 1.95×\n"
            "<code>/roulette 50 odd</code> / even · 1.95×\n"
            "<code>/roulette 50 17</code> exact · 35×",
            parse_mode="HTML",
            reply_markup=kb,
        )
        return
    if not await require_group(update, context):
        return
    if not await check_bot_and_game(update, context, data, "roulette"):
        return
    u = ensure_user(data, user)
    bal = float(u.get("balance", 0) or 0)
    a0, bet = args[0], args[1]
    if a0 in ("half", "1/2"):
        stake = round(bal / 2, 2)
    elif a0 in ("all", "allin", "all-in"):
        stake = round(bal, 2)
    else:
        try:
            stake = float(a0.replace(",", ""))
        except Exception:
            await msg.reply_text("Example: /roulette 50 red")
            return
    mn = min_bet_val(data)
    mx = float(data["settings"].get("max_bet", MAX_BET))
    if stake < mn or stake > mx:
        await msg.reply_text(f"Stake ₹{mn:.0f}–₹{mx:.0f}")
        return
    if bal < stake or not take_bal(data, str(user.id), stake):
        await msg.reply_text("Low balance!")
        return
    save(data)

    REDS = {1, 3, 5, 7, 9, 12, 14, 16, 18, 19, 21, 23, 25, 27, 30, 32, 34, 36}
    valid_named = {"red", "black", "odd", "even", "high", "low"}
    target_num = None
    if bet not in valid_named:
        try:
            target_num = int(bet)
            if target_num < 0 or target_num > 36:
                raise ValueError()
        except Exception:
            add_bal(data, str(user.id), stake)
            save(data)
            await msg.reply_text("Invalid bet. red/black/odd/even/high/low or 0–36")
            return

    # 1) THROW real Telegram slot dice — value is source of truth
    try:
        dice_msg = await context.bot.send_dice(chat_id=msg.chat_id, emoji="🎰")
        dice_val = int(dice_msg.dice.value)  # 1..64
    except Exception as e:
        add_bal(data, str(user.id), stake)
        save(data)
        await msg.reply_text(f"Dice failed, stake refunded. {e}")
        return

    # Map 🎰 1-64 → European pocket 0-36 (same value always → same n)
    n = (dice_val - 1) % 37
    color = "green" if n == 0 else ("red" if n in REDS else "black")

    # 2) Win ONLY from this n (never random after dice)
    if bet == "red":
        won, mult = (color == "red"), 1.95
    elif bet == "black":
        won, mult = (color == "black"), 1.95
    elif bet == "odd":
        won, mult = (n != 0 and n % 2 == 1), 1.95
    elif bet == "even":
        won, mult = (n != 0 and n % 2 == 0), 1.95
    elif bet == "high":
        won, mult = (19 <= n <= 36), 1.95
    elif bet == "low":
        won, mult = (1 <= n <= 18), 1.95
    else:
        won, mult = (n == target_num), 35.0

    # Optional house edge: only force loss by NOT paying — never change displayed n
    # (display always matches dice). Rig does not alter Landed number.

    fair = f"RL-D{dice_val}-N{n}-" + "".join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(4))
    if won:
        pay = round(float(stake) * float(mult), 2)
        add_bal(data, str(user.id), pay)
        record(data, str(user.id), "roulette", stake, True, pay)
        arrow = f"₹{stake:.2f} → ₹{pay:.2f}"
        mark = "✅"
    else:
        pay = 0.0
        record(data, str(user.id), "roulette", stake, False, 0)
        arrow = f"₹{stake:.2f} → ₹0.00"
        mark = "❌"
    save(data)

    await asyncio.sleep(0.4)
    pname = user.first_name or user.username or str(user.id)
    if bet in ("red", "black"):
        bet_show = f"Colors: {bet.title()}"
    elif bet in ("odd", "even", "high", "low"):
        bet_show = bet.title()
    else:
        bet_show = f"Number: {bet}"
    await msg.reply_text(
        f"🎰 <b>Roulette · Verify</b>\n\n"
        f"Player: <b>{pname}</b>\n"
        f"Dice: <code>{dice_val}</code> → Landed: <b>{n}</b> ({color.title()})\n"
        f"Your bets: {bet_show}\n"
        f"Bet: {arrow} {mark}\n"
        f"<code>{fair}</code>",
        parse_mode="HTML",
    )


async def cmd_russian(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Russian roulette — 1/6 chance die (lose), else win 1.15x
    /russian 50
    """
    if not await require_group(update, context):
        return
    data = load()
    if not await check_bot_and_game(update, context, data, "russian"):
        return
    user = update.effective_user
    u = ensure_user(data, user)
    try:
        stake = float((context.args or ["0"])[0])
    except Exception:
        stake = 0
    mn = min_bet_val(data)
    if stake < mn:
        await update.message.reply_text(
            f"🔫 <b>Russian Roulette</b>\n<code>/russian {int(mn)}</code>\n"
            f"1 chamber loaded · survive → 1.15× · Sticker: AxomRevolver",
            parse_mode="HTML",
        )
        return
    if float(u.get("balance", 0)) < stake or not take_bal(data, str(user.id), stake):
        await update.message.reply_text("Low balance!")
        return
    save(data)
    import random as _r
    chamber = _r.randint(1, 6)
    # under full rig, higher death chance
    rig = str(data.get("settings", {}).get("rig_mode", "off"))
    death_slots = {1}
    if rig == "full":
        death_slots = {1, 2, 3, 4}  # ~66%
    elif rig == "active":
        death_slots = {1, 2}  # ~33%
    dead = chamber in death_slots
    fair = "RR-" + "".join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(8))
    if dead:
        record(data, str(user.id), "russian", stake, False, 0)
        save(data)
        res = f"💥 BANG — You lose ₹{stake:.0f}"
    else:
        pay = round(stake * 1.15, 2)
        add_bal(data, str(user.id), pay)
        record(data, str(user.id), "russian", stake, True, pay)
        save(data)
        res = f"😌 Click… safe · +₹{pay:.2f} (1.15×)"
    await update.message.reply_text(
        f"🔫 <b>RUSSIAN ROULETTE</b>\n<blockquote>{res}\nChamber: {chamber}/6\n"
        f"Fair ID: <code>{fair}</code></blockquote>",
        parse_mode="HTML",
    )


async def cmd_rigmode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load()
    if not is_owner(data, update.effective_user.id):
        return
    mode = (context.args[0].lower() if context.args else "")
    if mode in ("off", "active", "full"):
        data["settings"]["rig_mode"] = mode
        save(data)
        await update.message.reply_text(f"✅ Rig mode: <b>{mode}</b>", parse_mode="HTML")
    else:
        await update.message.reply_text(
            f"Current: <b>{data['settings'].get('rig_mode','off')}</b>\n"
            f"/rigmode off | active | full",
            parse_mode="HTML",
        )


def main():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN is missing. Add it to Replit Secrets or set the BOT_TOKEN environment variable.")
    req = HTTPXRequest(connect_timeout=30.0, read_timeout=30.0)
    app = Application.builder().token(BOT_TOKEN).request(req).build()

    app.add_handler(CommandHandler("start", start))

    app.add_handler(CommandHandler(["currency", "cur"], cmd_currency))
    app.add_handler(CommandHandler("freeze", cmd_freeze))
    app.add_handler(CommandHandler("unfreeze", cmd_unfreeze))
    app.add_handler(CommandHandler(["setlimits", "limits"], cmd_setlimits))
    app.add_handler(CommandHandler(["loyalty", "loyal"], cmd_loyalty))
    app.add_handler(CommandHandler("redeem", cmd_redeem))
    app.add_handler(CommandHandler(["crypto", "wallets"], cmd_crypto))
    app.add_handler(CommandHandler(["roulette", "roul"], cmd_roulette))
    app.add_handler(CommandHandler(["crossy", "crossyroad", "chicken", "chickenroad"], cmd_crossyroad))
    app.add_handler(CommandHandler(["wheel"], cmd_wheel_help))
    # tower removed
    # app.add_handler(CommandHandler(["tower", "monkeytower", "monkey"], cmd_tower))
    app.add_handler(CommandHandler(["russian", "rr"], cmd_russian))
    app.add_handler(CommandHandler(["rigmode", "rig"], cmd_rigmode))
    app.add_handler(CommandHandler("commands", cmd_commands))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler(["support", "customersupport", "cs"], cmd_support))
    app.add_handler(CommandHandler(["wallet", "bal", "balance"], cmd_wallet))
    app.add_handler(CommandHandler("deposit", cmd_deposit))
    app.add_handler(CommandHandler("withdraw", cmd_withdraw))
    app.add_handler(CommandHandler("myid", cmd_myid))
    app.add_handler(CommandHandler(["invite", "referral"], cmd_invite))
    app.add_handler(CommandHandler("mystats", cmd_mystats))
    app.add_handler(CommandHandler("wagerstatus", cmd_wagerstatus))
    app.add_handler(CommandHandler("topwager", cmd_topwager))
    app.add_handler(CommandHandler(["leaderboard", "lb", "top"], cmd_leaderboard))
    app.add_handler(CommandHandler("bonus", cmd_bonus))
    app.add_handler(CommandHandler("cancel", cmd_cancel))
    app.add_handler(CommandHandler("allow", cmd_allow))
    app.add_handler(CommandHandler("disallow", cmd_disallow))
    app.add_handler(CommandHandler("allowlist", cmd_allowlist))
    app.add_handler(CommandHandler("crazy", cmd_crazy))
    app.add_handler(CommandHandler("dice", cmd_dice))
    app.add_handler(CommandHandler("dr", cmd_dr))
    app.add_handler(CommandHandler(["predict", "pred"], cmd_predict))
    app.add_handler(CommandHandler(["dj", "dicejack"], cmd_dj))
    app.add_handler(CommandHandler("basket", cmd_basket))
    app.add_handler(CommandHandler("football", cmd_football))
    app.add_handler(CommandHandler("bowl", cmd_bowl))
    app.add_handler(CommandHandler("dart", cmd_dart))
    app.add_handler(CommandHandler("slot", cmd_slot))
    app.add_handler(CommandHandler("slots", cmd_slot))
    app.add_handler(CommandHandler("bj", cmd_bj))
    app.add_handler(CommandHandler("blackjack", cmd_bj))
    app.add_handler(CommandHandler("coin", cmd_coin))
    app.add_handler(CommandHandler("battle", cmd_battle))
    app.add_handler(CommandHandler("rps", cmd_rps))
    app.add_handler(CommandHandler("mines", cmd_mines))
    app.add_handler(CommandHandler("jackpot", cmd_jackpot))

    app.add_handler(CommandHandler(["hb", "house", "botfund"], cmd_hb))
    app.add_handler(CommandHandler(["hbadd", "addhb", "houseadd"], cmd_hbadd))
    app.add_handler(CommandHandler(["cutbal", "cut", "deduct"], cmd_cutbal))
    app.add_handler(CommandHandler(["language", "lang", "lauage"], cmd_language))
    app.add_handler(CommandHandler("escrow", cmd_escrow))
    app.add_handler(CommandHandler("escrowaccept", cmd_escrowaccept))
    app.add_handler(CommandHandler("escrowrelease", cmd_escrowrelease))
    app.add_handler(CommandHandler("escrowcancel", cmd_escrowcancel))
    app.add_handler(CommandHandler("escrowlist", cmd_escrowlist))
    app.add_handler(CommandHandler(["payments", "paylog", "payhistory"], cmd_payments))
    app.add_handler(CommandHandler("jackpotdraw", cmd_jackpotdraw))

    app.add_handler(CommandHandler("tip", cmd_tip))
    app.add_handler(CommandHandler("promo", cmd_promo))
    app.add_handler(CommandHandler("makecode", cmd_makecode))
    app.add_handler(CommandHandler(["7up", "7down", "sevenup"], cmd_7up))
    app.add_handler(CommandHandler("limbo", cmd_limbo))
    app.add_handler(CommandHandler("rain", cmd_rain))
    app.add_handler(CommandHandler("addbotadmin", cmd_addbotadmin))
    app.add_handler(CommandHandler("removebotadmin", cmd_removebotadmin))
    app.add_handler(CommandHandler("setbrand", cmd_setbrand))

    app.add_handler(CommandHandler("addbal", cmd_addbal))
    app.add_handler(CommandHandler("addowner", cmd_addowner))
    app.add_handler(CommandHandler(["removeowner", "delowner"], cmd_removeowner))
    app.add_handler(CommandHandler("setgroup", cmd_setgroup))
    app.add_handler(CommandHandler("setgrouplink", cmd_setgrouplink))
    app.add_handler(CommandHandler("panel", cmd_panel))
    app.add_handler(CommandHandler(["admincommands", "adminhelp", "admin"], cmd_admincommands))
    app.add_handler(CommandHandler("setupi", cmd_setupi))
    app.add_handler(CommandHandler("setupiandqr", cmd_setupiandqr))
    app.add_handler(CommandHandler("stats", cmd_stats))
    app.add_handler(CommandHandler("ban", cmd_ban))
    app.add_handler(CommandHandler("unban", cmd_unban))
    app.add_handler(CommandHandler("on", cmd_on))
    app.add_handler(CommandHandler("off", cmd_off))

    # --- admin bot control (must be registered) ---
    app.add_handler(CommandHandler("setwallet", cmd_setwallet))
    app.add_handler(CommandHandler("creditbyamount", cmd_creditbyamount))
    app.add_handler(CommandHandler("setbinanceaddr", cmd_setbinanceaddr))
    app.add_handler(CommandHandler("boton", cmd_boton))
    app.add_handler(CommandHandler("botoff", cmd_botoff))
    app.add_handler(CommandHandler(["fixbot", "repair", "maintenance"], cmd_fixbot))
    app.add_handler(CommandHandler(["logs", "log", "viewlogs"], cmd_logs))
    app.add_handler(CommandHandler(["setwinschannel", "winschannel", "setlogchannel"], cmd_setwinschannel))
    app.add_handler(CommandHandler("setminibet", cmd_setminibet))
    app.add_handler(CommandHandler(["setmaxbet", "maxbet"], cmd_setmaxbet))
    app.add_handler(CommandHandler(["addgatewayupi", "setgateway"], cmd_addgatewayupi))
    app.add_handler(CommandHandler("setgatewaykey", cmd_setgatewaykey))
    app.add_handler(CommandHandler("setgatewaysecret", cmd_setgatewaysecret))
    app.add_handler(CommandHandler(["gatewaystatus", "gwstatus"], cmd_gatewaystatus))
    app.add_handler(CommandHandler("setmindeposit", cmd_setmindeposit))
    app.add_handler(CommandHandler(["announcement", "announce"], cmd_announcement))
    app.add_handler(CommandHandler(
        ["offgame", "offdice", "offdart", "offbowl", "offbasket", "offfootball",
         "offslot", "offbj", "offlimbo", "offcoin", "offrps", "offdr", "offmines"],
        cmd_offgame,
    ))
    app.add_handler(CommandHandler(
        ["ongame", "ondice", "ondart", "onbowl", "onbasket", "onfootball",
         "onslot", "onbj", "onlimbo", "oncoin", "onrps", "ondr", "onmines"],
        cmd_ongame,
    ))

    app.add_handler(CallbackQueryHandler(cb))
    app.add_handler(MessageHandler(filters.Dice.ALL, on_dice))
    app.add_handler(MessageHandler(filters.PHOTO, photo_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_router))

    async def _post(app_):
        cmds = [
            BotCommand("help", "All commands"),
            BotCommand("wallet", "Balance"),
            BotCommand("deposit", "Deposit"),
            BotCommand("withdraw", "Withdraw"),
            BotCommand("dice", "Dice game"),
            BotCommand("dart", "Darts"),
            BotCommand("bj", "Blackjack"),
            BotCommand("limbo", "Limbo"),
            BotCommand("dr", "Dice roulette"),
            BotCommand("slot", "Slots"),
            BotCommand("battle", "PvP battle"),
            BotCommand("escrow", "Secure escrow"),
            BotCommand("leaderboard", "Top players"),
            BotCommand("topwager", "Top wager photo"),
            BotCommand("mystats", "Stats card"),
            BotCommand("payments", "Payment history (DM)"),
            BotCommand("jackpot", "Jackpot"),
        ]
        try:
            await app_.bot.set_my_commands(cmds)
            await app_.bot.set_my_commands(cmds, scope=BotCommandScopeAllGroupChats())
            await app_.bot.set_my_commands(cmds, scope=BotCommandScopeAllPrivateChats())
        except Exception as e:
            logger.warning("set commands %s", e)
        # Axom-style wins channel logger (every 3s)
        try:
            if app_.job_queue:
                app_.job_queue.run_repeating(flush_wins_channel, interval=3, first=5, name="wins_feed")
                logger.info("wins channel job started")
        except Exception as e:
            logger.warning("job_queue wins feed: %s (pip install 'python-telegram-bot[job-queue]')", e)
    app.post_init = _post
    print(f"🔥 HR CASINO · Wins logger ready | Group {GROUP_ID}")
    app.run_polling(drop_pending_updates=True, allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
