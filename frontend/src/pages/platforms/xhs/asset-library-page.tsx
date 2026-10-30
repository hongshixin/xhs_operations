import { CloudUploadOutlined, FileImageOutlined, FolderOpenOutlined, LinkOutlined, PlusOutlined, ReloadOutlined, VideoCameraOutlined } from "@ant-design/icons";
import { Button, Card, DatePicker, Empty, Image, Input, Modal, Pagination, Select, Space, Tag, theme, Typography, Upload, message } from "antd";
import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";

import { PageHeader } from "../../../components/layout/app-shell";
import { addDraftAsset, createDraftFromNote, fetchAssetLibrary, fetchDrafts, startCapturePair, uploadAssetFile } from "../../../lib/api";
import type { Draft, LibraryAsset } from "../../../types";
import "./asset-library-page.css";

const { Text } = Typography;
const SOURCE_LABEL: Record<LibraryAsset["source"], string> = { upload: "本地上传", ai: "AI 生成", note: "笔记采集", web: "网页收藏" };
const PLATFORM_LABEL: Record<string, string> = { xhs: "小红书", douyin: "抖音", taobao: "淘宝", jd: "京东", other: "其他网站" };

export function XhsAssetLibraryPage() {
  const { token } = theme.useToken();
  const navigate = useNavigate();
  const [assets, setAssets] = useState<LibraryAsset[]>([]);
  const [drafts, setDrafts] = useState<Draft[]>([]);
  const [loading, setLoading] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [source, setSource] = useState("all");
  const [kind, setKind] = useState("all");
  const [keyword, setKeyword] = useState("");
  const [dates, setDates] = useState<[string, string] | null>(null);
  const [page, setPage] = useState(1);
  const [selected, setSelected] = useState<LibraryAsset | null>(null);
  const [draftId, setDraftId] = useState<number | "new" | null>(null);
  const [saving, setSaving] = useState(false);
  const [pairCode, setPairCode] = useState("");
  const [pairLoading, setPairLoading] = useState(false);

  async function load() {
    setLoading(true);
    try {
      const [library, draftResult] = await Promise.all([fetchAssetLibrary(), fetchDrafts("xhs", 100)]);
      setAssets(library.items);
      setDrafts(draftResult.items);
    } catch {
      message.error("素材加载失败，请稍后重试");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { void load(); }, []);

  async function uploadFile(file: File) {
    // 后端返回 duplicate 时复用旧文件，刷新列表即可展示原有素材。
    setUploading(true);
    try {
      const result = await uploadAssetFile(file);
      message.success(result.duplicate ? "该文件已在素材库中，已为你复用" : "素材上传成功");
      await load();
    } catch {
      message.error("上传失败，请检查文件格式和大小");
    } finally {
      setUploading(false);
    }
    return false;
  }

  // 筛选只改变当前视图，来源数据与原始文件保持不变。
  const filtered = useMemo(() => assets.filter((asset) => {
    if (source.startsWith("web:") && (asset.source !== "web" || asset.source_platform !== source.slice(4))) return false;
    if (source !== "all" && !source.startsWith("web:") && asset.source !== source) return false;
    if (kind !== "all" && asset.asset_type !== kind) return false;
    if (keyword && !asset.title.toLocaleLowerCase().includes(keyword.toLocaleLowerCase())) return false;
    const day = asset.created_at.slice(0, 10);
    return !dates || (day >= dates[0] && day <= dates[1]);
  }), [assets, source, kind, keyword, dates]);
  const visible = filtered.slice((page - 1) * 24, page * 24);

  async function addToDraft() {
    // 优先传本地文件名，发布流程可直接读取媒体文件；远程素材保留 URL。
    if (!selected || draftId === null) return;
    setSaving(true);
    try {
      const target = draftId === "new" ? await createDraftFromNote({ platform: "xhs", title: "" }) : drafts.find((draft) => draft.id === draftId);
      if (!target) throw new Error("Draft not found");
      await addDraftAsset(target.id, {
        asset_type: selected.asset_type,
        ...(selected.local_path ? { local_path: selected.local_path } : { url: selected.url }),
      });
      message.success("已加入草稿");
      setSelected(null);
      setDraftId(null);
      navigate("/platforms/xhs/drafts");
    } catch {
      message.error("加入草稿失败，请重试");
    } finally {
      setSaving(false);
    }
  }

  async function openPairCode() {
    setPairLoading(true);
    try {
      const result = await startCapturePair();
      setPairCode(result.code);
    } catch {
      message.error("配对码生成失败，请确认已经登录");
    } finally {
      setPairLoading(false);
    }
  }

  return (
    <div className="asset-library">
      <PageHeader eyebrow="XHS Asset Library" title="素材库" description="集中查看本地上传、AI 生成和笔记采集素材，找到后直接放入草稿。" action={<Button icon={<ReloadOutlined />} onClick={() => void load()} loading={loading}>刷新</Button>} />

      <Card className="asset-library-upload" styles={{ body: { padding: 0 } }}>
        <Upload.Dragger accept=".jpg,.jpeg,.png,.gif,.webp,.mp4,.mov,.avi,.mkv" multiple showUploadList={false} disabled={uploading} beforeUpload={(file) => { void uploadFile(file); return false; }}>
          <div className="asset-library-upload-inner">
            <span className="asset-library-upload-icon"><CloudUploadOutlined /></span>
            <div><Text strong>上传本地素材</Text><div><Text type="secondary">拖入图片或视频，也可以点击选择；相同文件会自动复用</Text></div></div>
            <Button type="primary" icon={<PlusOutlined />} loading={uploading}>选择文件</Button>
          </div>
        </Upload.Dragger>
      </Card>

      <Card className="asset-library-browser" styles={{ body: { padding: "16px 20px" } }}>
        <div><Text strong>浏览器一键收集</Text><div><Text type="secondary">安装项目内的浏览器插件，在网页上挑选图片或视频，直接保存到这里并记录来源。</Text></div></div>
        <Button icon={<LinkOutlined />} loading={pairLoading} onClick={() => void openPairCode()}>连接浏览器插件</Button>
      </Card>

      <Card className="asset-library-filter" styles={{ body: { padding: 16 } }}>
        <Space wrap size={12}>
          <Input.Search placeholder="搜索名称或 AI 提示词" allowClear value={keyword} onChange={(event) => { setKeyword(event.target.value); setPage(1); }} style={{ width: 250 }} />
          <Select aria-label="素材来源" value={source} onChange={(value) => { setSource(value); setPage(1); }} style={{ width: 160 }} options={[{ value: "all", label: "全部来源" }, ...Object.entries(SOURCE_LABEL).map(([value, label]) => ({ value, label })), ...Object.entries(PLATFORM_LABEL).map(([value, label]) => ({ value: `web:${value}`, label }))]} />
          <Select aria-label="素材类型" value={kind} onChange={(value) => { setKind(value); setPage(1); }} style={{ width: 130 }} options={[{ value: "all", label: "全部类型" }, { value: "image", label: "图片" }, { value: "video", label: "视频" }]} />
          <DatePicker.RangePicker onChange={(_, strings) => { setDates(strings[0] && strings[1] ? [strings[0], strings[1]] : null); setPage(1); }} />
        </Space>
      </Card>

      <div className="asset-library-heading"><Text strong>全部素材</Text><Text type="secondary">{filtered.length} 项</Text></div>
      {visible.length === 0 ? <Card><Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={loading ? "正在加载素材…" : "没有符合条件的素材"} /></Card> : (
        <div className="asset-library-grid">
          {visible.map((asset) => <Card key={asset.id} className="asset-library-card" hoverable styles={{ body: { padding: 0 } }}>
            <div className="asset-library-preview" style={{ background: token.colorFillQuaternary }}>
              {asset.asset_type === "image" ? <Image src={asset.url} alt={asset.title} preview={{ mask: "预览" }} fallback="" /> : <video src={asset.url} preload="metadata" controls aria-label={asset.title} />}
              <Tag className="asset-library-source" color={asset.source === "ai" ? "purple" : asset.source === "note" ? "blue" : asset.source === "web" ? "cyan" : "gold"}>{asset.source === "web" ? PLATFORM_LABEL[asset.source_platform || "other"] : SOURCE_LABEL[asset.source]}</Tag>
            </div>
            <div className="asset-library-card-content">
              <Text strong ellipsis={{ tooltip: asset.title }} className="asset-library-title">{asset.title}</Text>
              <div className="asset-library-meta"><Space size={6}>{asset.asset_type === "image" ? <FileImageOutlined /> : <VideoCameraOutlined />}{asset.created_at.slice(0, 10)}</Space>{asset.size !== null && <span>{(asset.size / 1024 / 1024).toFixed(1)} MB</span>}</div>
              {asset.source_url && <a className="asset-library-origin" href={asset.source_url} target="_blank" rel="noopener noreferrer"><LinkOutlined /> 查看来源页面</a>}
              <Button block icon={<FolderOpenOutlined />} onClick={() => { setSelected(asset); setDraftId(null); }}>加入草稿</Button>
            </div>
          </Card>)}
        </div>
      )}
      {filtered.length > 24 && <Pagination className="asset-library-pagination" current={page} pageSize={24} total={filtered.length} onChange={setPage} showSizeChanger={false} />}

      <Modal title="加入草稿" open={!!selected} onCancel={() => setSelected(null)} onOk={() => void addToDraft()} okText="加入草稿" okButtonProps={{ disabled: draftId === null, loading: saving }}>
        <Text type="secondary">选择已有草稿，或新建一个空白草稿。</Text>
        <Select style={{ width: "100%", marginTop: 16 }} placeholder="选择草稿" value={draftId} onChange={setDraftId} options={[{ value: "new", label: "＋ 新建草稿" }, ...drafts.map((draft) => ({ value: draft.id, label: draft.title || `未命名草稿 #${draft.id}` }))]} />
      </Modal>
      <Modal title="连接浏览器插件" open={!!pairCode} onCancel={() => setPairCode("")} footer={<Button onClick={() => setPairCode("")}>完成</Button>}>
        <p>打开浏览器插件，点击“连接本地素材库”，输入下面的配对码。配对码 5 分钟内有效，只能使用一次。</p>
        <Text code copyable style={{ fontSize: 20, letterSpacing: 2 }}>{pairCode}</Text>
        <p><Text type="secondary">插件安装步骤见项目文件夹中的 browser-extension/README.md。</Text></p>
      </Modal>
    </div>
  );
}
