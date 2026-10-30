const API = "http://127.0.0.1:1314/api/files/capture";
let token = "";
let page = null;

const $ = (id) => document.getElementById(id);

function status(text) { $("status").textContent = text; }

function showPanel(connected) {
  $("pair-panel").hidden = connected;
  $("capture-panel").hidden = !connected;
}

async function pair() {
  const code = $("pair-code").value.trim();
  if (!code) return status("请输入素材库显示的配对码");
  $("pair-button").disabled = true;
  try {
    const response = await fetch(`${API}/pair/complete`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ code }),
    });
    if (!response.ok) throw new Error((await response.json()).detail || "配对失败");
    token = (await response.json()).capture_token;
    await chrome.storage.local.set({ captureToken: token });
    showPanel(true);
    await scan();
  } catch (error) {
    status(`连接失败：${error.message}。请确认本地服务已启动。`);
  } finally {
    $("pair-button").disabled = false;
  }
}

async function scan() {
  status("");
  $("media-list").replaceChildren();
  try {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    if (!tab?.id || !/^https?:\/\//.test(tab.url || "")) throw new Error("请先打开要收集的网页");
    // 只读取用户当前打开的页面，不在后台遍历账号或批量抓取网页。
    const [result] = await chrome.scripting.executeScript({ target: { tabId: tab.id }, func: () => {
      const candidates = [];
      const seen = new Set();
      const add = (url, type, preview) => {
        if (!url || !/^https?:\/\//.test(url) || seen.has(url)) return;
        seen.add(url);
        candidates.push({ url, type, preview: preview || url });
      };
      for (const image of document.images) {
        if (image.naturalWidth >= 120 && image.naturalHeight >= 120) add(image.currentSrc || image.src, "image");
      }
      for (const video of document.querySelectorAll("video")) {
        add(video.currentSrc || video.src || video.querySelector("source")?.src, "video", video.poster);
      }
      for (const key of ["og:image", "og:video"]) {
        const value = document.querySelector(`meta[property="${key}"]`)?.content;
        add(value, key === "og:image" ? "image" : "video");
      }
      return { title: document.title, url: location.href, items: candidates.slice(0, 80) };
    } });
    page = result.result;
    $("page-title").textContent = page.title || "当前网页";
    $("count").textContent = `${page.items.length} 个可选素材`;
    for (const item of page.items) {
      const label = document.createElement("label");
      label.className = "media-item";
      const checkbox = document.createElement("input");
      checkbox.type = "checkbox";
      checkbox.checked = true;
      checkbox.value = item.url;
      const preview = document.createElement("img");
      preview.src = item.preview;
      preview.alt = item.type === "video" ? "视频预览" : "图片预览";
      label.append(checkbox, preview);
      if (item.type === "video") {
        const mark = document.createElement("span");
        mark.className = "video-mark";
        mark.textContent = "视频";
        label.append(mark);
      }
      $("media-list").append(label);
    }
    if (!page.items.length) status("当前页面没有找到可读取的图片或视频。可尝试滚动页面后重新扫描。");
  } catch (error) {
    status(`扫描失败：${error.message}`);
  }
}

function fileExtension(blob, mediaType, url) {
  const mime = blob.type.split(";")[0].toLowerCase();
  const known = { "image/jpeg": "jpg", "image/png": "png", "image/gif": "gif", "image/webp": "webp", "video/mp4": "mp4", "video/quicktime": "mov", "video/x-msvideo": "avi", "video/x-matroska": "mkv" };
  const ext = known[mime];
  if (ext && mime.startsWith(`${mediaType}/`)) return ext;
  // 部分平台把媒体标为二进制流；仅此情形才回退到可信的文件后缀。
  if (mime === "application/octet-stream") {
    const suffix = new URL(url).pathname.split(".").pop().toLowerCase();
    if ((mediaType === "image" ? ["jpg", "jpeg", "png", "gif", "webp"] : ["mp4", "mov", "avi", "mkv"]).includes(suffix)) return suffix;
  }
  throw new Error("文件格式暂不支持");
}

async function collect() {
  if (!page) return;
  const chosen = [...$("media-list").querySelectorAll("input:checked")].map((input) => page.items.find((item) => item.url === input.value));
  if (!chosen.length) return status("请先选择至少一项素材");
  $("collect-button").disabled = true;
  let saved = 0;
  let duplicates = 0;
  const errors = [];
  for (let index = 0; index < chosen.length; index += 1) {
    const item = chosen[index];
    status(`正在保存 ${index + 1}/${chosen.length}…`);
    try {
      // 扩展读取当前用户可见的媒体，再传给本地服务；服务端不会抓取任意 URL。
      const mediaResponse = await fetch(item.url, { credentials: "include" });
      if (!mediaResponse.ok) throw new Error(`媒体请求返回 ${mediaResponse.status}`);
      if (Number(mediaResponse.headers.get("content-length") || 0) > 100 * 1024 * 1024) throw new Error("单个文件超过 100MB");
      const blob = await mediaResponse.blob();
      if (blob.size > 100 * 1024 * 1024) throw new Error("单个文件超过 100MB");
      const ext = fileExtension(blob, item.type, item.url);
      const body = new FormData();
      body.append("file", blob, `网页素材-${index + 1}.${ext}`);
      body.append("source_url", page.url);
      body.append("title", page.title || "网页素材");
      const response = await fetch(`${API}/collect`, { method: "POST", headers: { Authorization: `Bearer ${token}` }, body });
      if (response.status === 401) {
        token = "";
        await chrome.storage.local.remove("captureToken");
        showPanel(false);
        throw new Error("插件授权已过期，请在素材库重新获取配对码");
      }
      if (!response.ok) throw new Error((await response.json()).detail || `保存失败 ${response.status}`);
      if ((await response.json()).duplicate) duplicates += 1;
      else saved += 1;
    } catch (error) {
      errors.push(`${index + 1}: ${error.message}`);
      if (!token) break;
    }
  }
  $("collect-button").disabled = false;
  status(`已保存 ${saved} 项，复用 ${duplicates} 项，失败 ${errors.length} 项${errors.length ? `（${errors.slice(0, 2).join("；")}）` : ""}。`);
}

$("pair-button").addEventListener("click", () => void pair());
$("refresh-button").addEventListener("click", () => void scan());
$("select-all").addEventListener("click", () => {
  const inputs = [...$("media-list").querySelectorAll("input[type=checkbox]")];
  const next = inputs.some((input) => !input.checked);
  inputs.forEach((input) => { input.checked = next; });
});
$("collect-button").addEventListener("click", () => void collect());

void chrome.storage.local.get("captureToken").then((stored) => {
  token = stored.captureToken || "";
  showPanel(Boolean(token));
  if (token) void scan();
});
