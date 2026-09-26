#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import time
import requests
from urllib.parse import quote


# =========================
# 环境变量
# =========================

EMAIL = os.environ.get("EMAIL") or ""
PASSWORD = os.environ.get("PASSWORD") or ""

TG_CHAT_ID = os.environ.get("TG_CHAT_ID") or ""
TG_BOT_TOKEN = os.environ.get("TG_BOT_TOKEN") or ""


# =========================
# 配置
# =========================

BASE_URL = "https://api.hcnsec.cn"

# new-api 默认：
# 500000 quota = 1$
QUOTA_PER_UNIT = 500000

# 当前站点暂未开启 Turnstile
TURNSTILE_TOKEN = ""


# =========================
# 工具函数
# =========================

def print_json_debug(title, data):
    """打印 API 返回结果，方便排查接口结构变化。"""
    print("\n" + "=" * 60)
    print(title)
    print("=" * 60)

    try:
        print(data)
    except Exception:
        print(repr(data))

    print("=" * 60)


def extract_user_id(data):
    """
    尝试从不同的新/旧 API 返回结构中提取用户 ID。

    支持例如：

    {
        "data": {
            "id": 123
        }
    }

    或：

    {
        "data": {
            "user": {
                "id": 123
            }
        }
    }

    或：

    {
        "data": {
            "user_id": 123
        }
    }
    """

    if not isinstance(data, dict):
        return None

    # 第一层 data
    user_data = data.get("data")

    if isinstance(user_data, dict):

        # 直接 data.id
        for key in ("id", "user_id", "userId"):
            value = user_data.get(key)

            if value is not None and str(value).strip():
                return value

        # data.user
        nested_user = user_data.get("user")

        if isinstance(nested_user, dict):
            for key in ("id", "user_id", "userId"):
                value = nested_user.get(key)

                if value is not None and str(value).strip():
                    return value

        # data.data
        nested_data = user_data.get("data")

        if isinstance(nested_data, dict):
            for key in ("id", "user_id", "userId"):
                value = nested_data.get(key)

                if value is not None and str(value).strip():
                    return value

    # 极少数接口可能直接返回 user_id
    for key in ("id", "user_id", "userId"):
        value = data.get(key)

        if value is not None and str(value).strip():
            return value

    return None


def extract_username(data):
    """尝试从常见结构中获取用户名。"""

    if not isinstance(data, dict):
        return ""

    user_data = data.get("data")

    if isinstance(user_data, dict):

        for key in ("username", "name", "email"):
            value = user_data.get(key)

            if value:
                return str(value)

        nested_user = user_data.get("user")

        if isinstance(nested_user, dict):
            for key in ("username", "name", "email"):
                value = nested_user.get(key)

                if value:
                    return str(value)

    for key in ("username", "name", "email"):
        value = data.get(key)

        if value:
            return str(value)

    return ""


# =========================
# 登录
# =========================

def login(session: requests.Session):
    """登录并返回用户信息。"""

    login_url = (
        f"{BASE_URL}/api/user/login"
        f"?turnstile={quote(TURNSTILE_TOKEN)}"
    )

    headers = {
        "Accept": "application/json, text/plain, */*",
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0",
        "Origin": BASE_URL,
        "Referer": f"{BASE_URL}/login",
    }

    payload = {
        "username": EMAIL,
        "password": PASSWORD,
    }

    try:
        resp = session.post(
            login_url,
            headers=headers,
            json=payload,
            timeout=20,
        )
    except requests.RequestException as e:
        print("登录请求异常:", e)
        return None

    print(f"登录 HTTP 状态码: {resp.status_code}")

    if resp.status_code != 200:
        print("登录请求失败:")
        print(resp.text[:2000])
        return None

    try:
        data = resp.json()
    except ValueError:
        print("登录接口返回的不是合法 JSON:")
        print(resp.text[:2000])
        return None

    # DEBUG：完整显示登录接口返回
    print_json_debug("DEBUG：登录接口返回", data)

    if not data.get("success"):
        print("登录失败:", data.get("message", ""))
        return None

    # 自动提取 ID
    user_id = extract_user_id(data)

    # 自动提取用户名
    username = extract_username(data)

    if not user_id:
        print("⚠️ 登录接口 success=true，但仍未找到用户 ID。")
        print("请检查上面的 DEBUG 返回结构。")
        return None

    print(
        f"✅ 登录成功 | 账户: "
        f"{username or EMAIL} | ID: {user_id}"
    )

    # 显示 Cookie
    if session.cookies:
        print("✅ 登录 Cookie 已保存:")
        for cookie in session.cookies:
            print(f"   {cookie.name}={cookie.value[:20]}...")

    return {
        "id": user_id,
        "username": username or EMAIL,
    }


# =========================
# 获取用户信息
# =========================

def get_user_info(session: requests.Session, user_id):
    """获取用户信息。"""

    url = f"{BASE_URL}/api/user/self"

    headers = {
        "Accept": "application/json, text/plain, */*",
        "User-Agent": "Mozilla/5.0",
        "Referer": BASE_URL,
        "New-Api-User": str(user_id),
    }

    try:
        resp = session.get(
            url,
            headers=headers,
            timeout=20,
        )
    except requests.RequestException as e:
        print("获取用户信息请求异常:", e)
        return None

    print(f"用户信息 HTTP 状态码: {resp.status_code}")

    try:
        data = resp.json()
    except ValueError:
        print("用户信息接口返回的不是 JSON:")
        print(resp.text[:2000])
        return None

    # DEBUG
    print_json_debug("DEBUG：/api/user/self 返回", data)

    if data.get("success"):
        return data.get("data", {})

    print(
        "获取用户信息失败:",
        data.get("message", "")
    )

    return None


# =========================
# 签到
# =========================

def checkin(session: requests.Session, user_id):
    """执行签到。"""

    url = f"{BASE_URL}/api/user/checkin"

    headers = {
        "Accept": "application/json, text/plain, */*",
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0",
        "Origin": BASE_URL,
        "Referer": BASE_URL,
        "New-Api-User": str(user_id),
    }

    try:
        resp = session.post(
            url,
            headers=headers,
            json={},
            timeout=20,
        )
    except requests.RequestException as e:
        print("签到请求异常:", e)
        return {
            "success": False,
            "message": str(e),
        }

    print(f"签到 HTTP 状态码: {resp.status_code}")

    try:
        data = resp.json()
    except ValueError:
        print("签到接口返回的不是 JSON:")
        print(resp.text[:2000])

        return {
            "success": False,
            "message": f"HTTP {resp.status_code}，返回非 JSON",
        }

    # DEBUG
    print_json_debug("DEBUG：/api/user/checkin 返回", data)

    return data


# =========================
# quota 转美元
# =========================

def quota_to_dollar(quota):
    """将内部 quota 转换成美元金额。"""

    try:
        quota = int(quota or 0)
    except (ValueError, TypeError):
        quota = 0

    return round(quota / QUOTA_PER_UNIT)


# =========================
# Telegram
# =========================

def send_notification(message):

    print("\n" + "=" * 25)
    print(message)
    print("=" * 25)

    if not TG_BOT_TOKEN or not TG_CHAT_ID:
        print(
            "未配置 TG_BOT_TOKEN / TG_CHAT_ID，"
            "跳过 Telegram 推送"
        )
        return

    try:

        tg_url = (
            f"https://api.telegram.org/"
            f"bot{TG_BOT_TOKEN}/sendMessage"
        )

        resp = requests.post(
            tg_url,
            json={
                "chat_id": TG_CHAT_ID,
                "text": message,
            },
            timeout=10,
        )

        if resp.status_code == 200:
            print("Telegram 通知发送成功")
        else:
            print(
                "Telegram 通知发送失败:",
                resp.status_code,
                resp.text[:1000],
            )

    except Exception as e:
        print("Telegram 通知发送异常:", e)


# =========================
# 主程序
# =========================

def main():

    # -------------------------
    # 检查环境变量
    # -------------------------

    if not EMAIL or not PASSWORD:

        print(
            "请先设置 EMAIL 和 PASSWORD "
            "环境变量。"
        )

        sys.exit(1)

    print("=" * 60)
    print("iamhc 自动签到")
    print("=" * 60)

    print("账户:", EMAIL)
    print("API:", BASE_URL)

    # -------------------------
    # Session
    # -------------------------

    session = requests.Session()

    session.headers.update({
        "User-Agent": "Mozilla/5.0",
    })

    # -------------------------
    # 登录
    # -------------------------

    user = login(session)

    if not user:

        print("\n❌ 登录失败，无法继续签到")

        sys.exit(1)

    user_id = user["id"]
    username = user.get(
        "username",
        str(user_id),
    )

    # -------------------------
    # 获取签到前余额
    # -------------------------

    print("\n正在获取签到前余额...")

    info_before = get_user_info(
        session,
        user_id,
    )

    if not info_before:

        print("❌ 获取用户信息失败")

        sys.exit(1)

    balance_before = quota_to_dollar(
        info_before.get("quota", 0)
    )

    print(
        f"💰 签到前余额: "
        f"{balance_before}$"
    )

    # -------------------------
    # 签到
    # -------------------------

    print("\n正在执行签到...")

    checkin_data = checkin(
        session,
        user_id,
    )

    # -------------------------
    # 获取签到后余额
    # -------------------------

    print("\n正在获取签到后余额...")

    info_after = get_user_info(
        session,
        user_id,
    )

    if not info_after:

        print("❌ 获取签到后用户信息失败")

        sys.exit(1)

    balance_after = quota_to_dollar(
        info_after.get("quota", 0)
    )

    # -------------------------
    # 当前时间
    # -------------------------

    local_time = time.gmtime(
        time.time() + 8 * 3600
    )

    now = time.strftime(
        "%Y-%m-%d %H:%M:%S",
        local_time,
    )

    # -------------------------
    # 判断签到结果
    # -------------------------

    success = checkin_data.get(
        "success",
        False,
    )

    msg = str(
        checkin_data.get(
            "message",
            "",
        )
    )

    if success:

        awarded_data = checkin_data.get(
            "data",
            {},
        )

        if not isinstance(
            awarded_data,
            dict,
        ):
            awarded_data = {}

        awarded_quota = awarded_data.get(
            "quota_awarded",
            0,
        )

        if awarded_quota:

            awarded_dollar = quota_to_dollar(
                awarded_quota
            )

        else:

            awarded_dollar = (
                balance_after -
                balance_before
            )

        print(
            f"✅ 签到成功 | "
            f"获得: {awarded_dollar}$"
        )

        message = (
            f"🎁 iamhc 签到通知\n\n"
            f"✅ 签到成功,本次签到获得"
            f"{awarded_dollar}$\n"
            f"👤 登录账户: {username}\n"
            f"💰 昨日余额: {balance_before}$\n"
            f"💰 当前余额: {balance_after}$\n"
            f"⏱️ 签到时间: {now}"
        )

    elif (
        "已签到" in msg
        or "重复签到" in msg
        or "今天已签到" in msg
    ):

        print(
            f"✅ 今日已签到 | "
            f"当前余额: {balance_after}$"
        )

        message = (
            f"🎁 iamhc 签到通知\n\n"
            f"✅ 今日你已经签到过了！\n"
            f"👤 登录账户: {username}\n"
            f"💰 昨日余额: {balance_before}$\n"
            f"💰 当前余额: {balance_after}$\n"
            f"⏱️ 签到时间: {now}"
        )

    else:

        print(
            f"❌ 签到失败 | {msg}"
        )

        message = (
            f"🎁 iamhc 签到通知\n\n"
            f"❌ 签到失败: {msg}\n"
            f"👤 登录账户: {username}\n"
            f"💰 昨日余额: {balance_before}$\n"
            f"💰 当前余额: {balance_after}$\n"
            f"⏱️ 签到时间: {now}"
        )

    # -------------------------
    # Telegram
    # -------------------------

    send_notification(message)


# =========================
# Entry
# =========================

if __name__ == "__main__":
    main()
