from __future__ import annotations

from typing import Any, Callable

from backend.app.adapters.xhs.login_runtime import LoginRuntimeStore
from backend.app.adapters.xhs.request_env import direct_xhs_request_env


class XhsCreatorLoginAdapter:
    def __init__(
        self,
        creator_qr_api_factory: Callable[[], Any] | None = None,
        creator_phone_api_factory: Callable[[], Any] | None = None,
    ):
        self._creator_qr_api_factory = creator_qr_api_factory or self._new_creator_qr_api
        self._creator_phone_api_factory = creator_phone_api_factory or self._new_creator_qr_api
        self._qr_clients = LoginRuntimeStore()
        self._phone_clients = LoginRuntimeStore()

    @staticmethod
    def _new_creator_qr_api() -> Any:
        from apis.xhs_creator_login_v2 import XHSCreatorLoginApi

        return XHSCreatorLoginApi()

    def exchange_from_user_cookies(self, user_cookies: dict[str, Any]) -> dict[str, Any]:
        with direct_xhs_request_env():
            from apis.xhs_creator_login_apis import XHSCreatorLoginApi

            api = XHSCreatorLoginApi()
            success, message, payload = api.exchange_creator_session_from_user_cookies(dict(user_cookies))
        if not success or not payload:
            raise RuntimeError(message)
        return {"status": "confirmed", "cookies": payload["cookies"]}

    def create_qrcode(self) -> dict[str, Any]:
        # Creator 需要完整的匿名设备会话与安全初始化，不能只生成基础 Cookie 后直接请求二维码。
        with direct_xhs_request_env():
            api = self._creator_qr_api_factory()
            try:
                for attempt in range(16):
                    cookies, session = api._prepare_login_session()
                    api._complete_security()
                    if session["active"]:
                        raise RuntimeError("当前 Creator 设备会话已登录，请刷新二维码")
                    success, message, payload = api.generate_qrcode(api.profile.cookie_map)
                    if success and payload:
                        break
                    if attempt == 15:
                        raise RuntimeError(message)
                    api._reset_anonymous_session()
                self._qr_clients.add(payload["qr_id"], api)
            except Exception:
                api.close()
                raise
        return {
            "cookies": payload["cookies"],
            "qr_id": payload["qr_id"],
            "qr_url": payload["qr_url"],
        }

    def check_qrcode_status(self, qr_id: str, cookies: dict[str, Any]) -> dict[str, Any]:
        runtime = self._qr_clients.get(qr_id)
        with direct_xhs_request_env():
            with runtime.lock:
                detail = runtime.api.query_qrcode_status(qr_id)
                code = detail["status"]
                updated_cookies = detail["cookies"]
                user_info = None
                if detail["success"]:
                    verified, data, updated_cookies = runtime.api.get_user_info(updated_cookies)
                    if not verified:
                        raise RuntimeError("扫码已确认，但 Creator 登录会话验证失败")
                    user_info = self._serialize_user_info(data)
        # 状态使用平台返回的数值；异常码直接报错，避免页面无限轮询。
        status = {1: "confirmed", 2: "pending", 3: "scanned", 4: "expired"}.get(code)
        if status is None or (status == "confirmed" and user_info is None):
            raise RuntimeError(f"Creator 二维码状态异常: {detail['message']}")
        if status in {"confirmed", "expired"}:
            self._qr_clients.discard(qr_id)
        return {"status": status, "cookies": updated_cookies, "user_info": user_info}

    def get_user_info(self, cookies: dict[str, Any]) -> dict[str, Any]:
        with direct_xhs_request_env():
            from apis.xhs_creator_login_apis import XHSCreatorLoginApi

            api = XHSCreatorLoginApi()
            success, data, _ = api.get_user_info(cookies)
        if not success:
            raise RuntimeError("Failed to fetch XHS Creator user info")
        return self._serialize_user_info(data)

    @staticmethod
    def _serialize_user_info(data: dict[str, Any]) -> dict[str, Any]:
        # 二维码与短信登录共用同一账号字段映射，保持入库结构一致。
        return {
            "external_user_id": data.get("userId", ""),
            "nickname": data.get("userName", ""),
            "avatar_url": data.get("userAvatar", ""),
            "profile": {
                "red_id": data.get("redId") or data.get("red_id") or "",
                "role": data.get("role") or "",
                "real_name_verified": data.get("realNameVerified"),
                "followers": data.get("fans") or data.get("followers") or data.get("followerCount"),
                "following": data.get("follows") or data.get("following") or data.get("followingCount"),
                "likes": data.get("likedCount") or data.get("likes") or data.get("likeCount"),
                "raw": data,
            },
        }

    def create_phone_session(self, phone: str) -> dict[str, Any]:
        # Creator 先走完整安全初始化；发送失败时重建匿名设备会话，与上游短信流程保持一致。
        with direct_xhs_request_env():
            api = self._creator_phone_api_factory()
            try:
                for attempt in range(16):
                    cookies, session = api._prepare_login_session()
                    api._complete_security()
                    if session["active"]:
                        raise RuntimeError("当前 Creator 设备会话已登录，请重新开始绑定")
                    cookies = api.profile.cookie_map
                    success, message, _ = api.send_phone_code(phone, cookies)
                    if success:
                        break
                    if attempt == 15:
                        raise RuntimeError(message)
                    api._reset_anonymous_session()
                self._phone_clients.add(cookies["a1"], api, subject=phone)
            except Exception:
                api.close()
                raise
        return {"cookies": cookies, "message": message or "sent"}

    def confirm_phone_login(self, phone: str, code: str, cookies: dict[str, Any]) -> dict[str, Any]:
        runtime = self._phone_clients.get(cookies.get("a1", ""))
        if runtime.subject != phone:
            raise RuntimeError("手机号与发送验证码时不一致")
        with direct_xhs_request_env():
            with runtime.lock:
                success, message, payload = runtime.api.login_by_phone(phone, code, cookies)
                if not success or not payload:
                    raise RuntimeError(message)
                verified, data, authenticated_cookies = runtime.api.get_user_info(payload["cookies"])
                if not verified:
                    raise RuntimeError("短信验证已通过，但 Creator 登录会话验证失败")
                user_info = self._serialize_user_info(data)
        self._phone_clients.discard(cookies["a1"])
        return {"status": "confirmed", "cookies": authenticated_cookies, "user_info": user_info}
