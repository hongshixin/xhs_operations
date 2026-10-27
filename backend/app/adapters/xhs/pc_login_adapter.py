from __future__ import annotations

from typing import Any, Callable

from backend.app.adapters.xhs.login_runtime import LoginRuntimeStore
from backend.app.adapters.xhs.request_env import direct_xhs_request_env


class XhsPcLoginAdapter:
    def __init__(
        self,
        pc_qr_api_factory: Callable[[], Any] | None = None,
        pc_phone_api_factory: Callable[[], Any] | None = None,
    ):
        self._pc_qr_api_factory = pc_qr_api_factory or self._new_pc_qr_api
        self._pc_phone_api_factory = pc_phone_api_factory or self._new_pc_qr_api
        self._qr_clients = LoginRuntimeStore()
        self._phone_clients = LoginRuntimeStore()

    @staticmethod
    def _new_pc_qr_api() -> Any:
        from apis.xhs_pc_login_v2 import XHSLoginApi

        return XHSLoginApi()

    def create_qrcode(self) -> dict[str, Any]:
        # PC 扫码需按新版 SDK 的浏览器顺序完成首次轮询和指纹上报，再向用户展示二维码。
        with direct_xhs_request_env():
            api = self._pc_qr_api_factory()
            try:
                cookies = api.generate_init_cookies()
                success, message, payload = api.generate_qrcode(cookies)
                if not success or not payload:
                    raise RuntimeError(message)
                checked, message, cookies = api.check_qrcode_status(payload["qr_id"], payload["code"], payload["cookies"])
                if checked or "扫描" not in message:
                    raise RuntimeError(f"二维码初始状态异常: {message}")
                api.ensure_webprofile(cookies)
                self._qr_clients.add(payload["qr_id"], api)
            except Exception:
                api.close()
                raise
        return {
            "cookies": cookies,
            "qr_id": payload["qr_id"],
            "code": payload["code"],
            "qr_url": payload["qr_url"],
        }

    def check_qrcode_status(self, qr_id: str, code: str, cookies: dict[str, Any]) -> dict[str, Any]:
        runtime = self._qr_clients.get(qr_id)
        with direct_xhs_request_env():
            with runtime.lock:
                success, message, updated_cookies = runtime.api.check_qrcode_status(qr_id, code, cookies)
                user_info = None
                if success:
                    verified, data, updated_cookies = runtime.api.get_user_info(updated_cookies)
                    if not verified or data.get("guest") is not False:
                        raise RuntimeError("扫码已确认，但 PC 登录会话验证失败")
                    user_info = self._serialize_user_info(data)
        if success:
            status = "confirmed"
        elif "过期" in message or "expired" in message.lower():
            status = "expired"
        elif "确认" in message or "confirm" in message.lower():
            status = "scanned"
        elif "扫描" in message or "scan" in message.lower():
            status = "pending"
        else:
            # 未知状态不能伪装成等待扫码，否则页面会无限轮询。
            raise RuntimeError(f"PC 二维码状态异常: {message}")
        if status in {"confirmed", "expired"}:
            self._qr_clients.discard(qr_id)
        return {"status": status, "cookies": updated_cookies, "user_info": user_info}

    def get_user_info(self, cookies: dict[str, Any]) -> dict[str, Any]:
        with direct_xhs_request_env():
            from apis.xhs_pc_login_apis import XHSLoginApi

            api = XHSLoginApi()
            success, data, _ = api.get_user_info(cookies)
        if not success:
            raise RuntimeError("Failed to fetch XHS user info")
        return self._serialize_user_info(data)

    @staticmethod
    def _serialize_user_info(data: dict[str, Any]) -> dict[str, Any]:
        # 二维码与短信登录共用同一账号字段映射，保持入库结构一致。
        return {
            "external_user_id": data.get("user_id", ""),
            "nickname": data.get("nickname", ""),
            "avatar_url": data.get("images") or data.get("imageb") or "",
            "profile": {
                "red_id": data.get("red_id") or data.get("redId") or "",
                "followers": data.get("fans") or data.get("followers") or data.get("follower_count"),
                "following": data.get("follows") or data.get("following") or data.get("following_count"),
                "likes": data.get("liked_count") or data.get("likes") or data.get("like_count"),
                "raw": data,
            },
        }

    def create_phone_session(self, phone: str) -> dict[str, Any]:
        # 短信发送前沿用新版 PC 匿名设备初始化，确认时复用同一签名和 Cookie 状态。
        with direct_xhs_request_env():
            api = self._pc_phone_api_factory()
            try:
                cookies = api.generate_init_cookies()
                api.ensure_webprofile(cookies)
                success, message, _ = api.send_phone_code(phone, cookies)
                if not success:
                    raise RuntimeError(message)
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
                if not verified or data.get("guest") is not False:
                    raise RuntimeError("短信验证已通过，但 PC 登录会话验证失败")
                user_info = self._serialize_user_info(data)
        self._phone_clients.discard(cookies["a1"])
        return {"status": "confirmed", "cookies": authenticated_cookies, "user_info": user_info}
