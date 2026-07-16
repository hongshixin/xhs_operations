import {
  ApiOutlined,
  ArrowDownOutlined,
  ArrowUpOutlined,
  CloudServerOutlined,
  DatabaseOutlined,
  DesktopOutlined,
  HddOutlined,
  ReloadOutlined,
  ThunderboltOutlined,
  WifiOutlined,
} from "@ant-design/icons";
import {
  Alert,
  Badge,
  Button,
  Card,
  Col,
  Progress,
  Row,
  Spin,
  Statistic,
  Table,
  Tag,
  Typography,
} from "antd";
import { useEffect, useRef, useState } from "react";

import { PageHeader } from "../../components/layout/app-shell";
import { fetchSystemStats } from "../../lib/api";
import type { SystemStats } from "../../types";

const { Text } = Typography;

const cardStyle = { background: "#1f1f1f", borderColor: "#303030" };
const innerCardStyle = { background: "#262626", borderColor: "#303030" };

function uptime(seconds: number): string {
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = seconds % 60;
  if (h > 0) return `${h}h ${m}m`;
  if (m > 0) return `${m}m ${s}s`;
  return `${s}s`;
}

function progressColor(pct: number): string {
  if (pct >= 90) return "#ef4444";
  if (pct >= 70) return "#f59e0b";
  return "#22c55e";
}

export function SystemStatsPage() {
  const [stats, setStats] = useState<SystemStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [autoRefresh, setAutoRefresh] = useState(true);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  async function load() {
    setError(null);
    try {
      const data = await fetchSystemStats();
      setStats(data);
    } catch {
      setError("获取系统状态失败");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
  }, []);

  useEffect(() => {
    if (autoRefresh) {
      timerRef.current = setInterval(() => void load(), 10_000);
    } else {
      if (timerRef.current) clearInterval(timerRef.current);
    }
    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, [autoRefresh]);

  if (loading) {
    return (
      <div style={{ textAlign: "center", padding: "80px 0" }}>
        <Spin size="large" tip="加载中..." />
      </div>
    );
  }

  if (!stats) {
    return (
      <Alert type="error" message={error || "数据加载失败"} showIcon />
    );
  }

  const memory = stats.memory ?? { system_total_mb: 0, system_used_mb: 0, system_free_mb: 0, system_used_pct: 0, process_rss_mb: 0, process_vms_mb: 0 };
  const cpu = stats.cpu ?? { cpu_pct: 0, cpu_count: 0, uptime_seconds: 0 };
  const storage = stats.storage ?? { db_size_mb: null, storage_size_mb: 0, disk_total_gb: 0, disk_used_gb: 0, disk_free_gb: 0, disk_used_pct: 0 };
  const database = stats.database ?? { notes: 0, note_assets: 0, note_comments: 0, ai_drafts: 0, ai_generated_assets: 0, accounts: 0, publish_jobs: 0, tasks_total: 0, tasks_by_status: {} };
  const network = stats.network ?? {
    sent_total_mb: 0, recv_total_mb: 0,
    send_rate_kbps: 0, recv_rate_kbps: 0,
    packets_sent: 0, packets_recv: 0,
    errin: 0, errout: 0, dropin: 0, dropout: 0,
    connections: -1, interfaces: [],
  };

  function fmtRate(kbps: number): string {
    if (kbps >= 1024) return `${(kbps / 1024).toFixed(1)} MB/s`;
    return `${kbps.toFixed(1)} KB/s`;
  }

  function fmtNum(n: number): string {
    if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
    if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`;
    return String(n);
  }

  // 任务状态表格
  const taskRows = Object.entries(database.tasks_by_status || {}).map(([status, cnt]) => ({
    status,
    count: cnt,
  }));

  // 数据库记录数
  const dbRows = [
    { label: "笔记", key: "notes", value: database.notes },
    { label: "笔记素材", key: "assets", value: database.note_assets },
    { label: "评论", key: "comments", value: database.note_comments },
    { label: "AI 草稿", key: "drafts", value: database.ai_drafts },
    { label: "AI 生成图片", key: "gen_assets", value: database.ai_generated_assets },
    { label: "平台账号", key: "accounts", value: database.accounts },
    { label: "发布任务", key: "publish", value: database.publish_jobs },
  ];

  return (
    <div>
      <PageHeader
        eyebrow="System"
        title="系统监控"
        description="实时查看内存、CPU、磁盘、网络流量及数据库各表记录数。"
        action={
          <div style={{ display: "flex", gap: 8 }}>
            <Button
              size="small"
              type={autoRefresh ? "primary" : "default"}
              onClick={() => setAutoRefresh((v) => !v)}
            >
              {autoRefresh ? "自动刷新 10s" : "已暂停"}
            </Button>
            <Button icon={<ReloadOutlined />} onClick={load} loading={loading}>
              刷新
            </Button>
          </div>
        }
      />

      {error && (
        <Alert type="error" message={error} showIcon closable style={{ marginBottom: 16 }} />
      )}

      <Row gutter={[16, 16]}>
        {/* ===== 内存 ===== */}
        <Col xs={24} md={12} lg={8}>
          <Card
            title={<span><DesktopOutlined style={{ marginRight: 6 }} />内存</span>}
            style={cardStyle}
          >
            <Progress
              percent={memory.system_used_pct}
              strokeColor={progressColor(memory.system_used_pct)}
              format={(p) => `${p}%`}
              style={{ marginBottom: 16 }}
            />
            <Row gutter={12}>
              <Col span={8}>
                <Statistic
                  title={<Text type="secondary" style={{ fontSize: 12 }}>总量</Text>}
                  value={memory.system_total_mb}
                  suffix="MB"
                  valueStyle={{ fontSize: 14 }}
                />
              </Col>
              <Col span={8}>
                <Statistic
                  title={<Text type="secondary" style={{ fontSize: 12 }}>已用</Text>}
                  value={memory.system_used_mb}
                  suffix="MB"
                  valueStyle={{ fontSize: 14, color: progressColor(memory.system_used_pct) }}
                />
              </Col>
              <Col span={8}>
                <Statistic
                  title={<Text type="secondary" style={{ fontSize: 12 }}>可用</Text>}
                  value={memory.system_free_mb}
                  suffix="MB"
                  valueStyle={{ fontSize: 14 }}
                />
              </Col>
            </Row>
            <Card size="small" style={{ ...innerCardStyle, marginTop: 12 }}>
              <Text type="secondary" style={{ fontSize: 12 }}>进程占用（RSS）</Text>
              <div style={{ fontSize: 18, fontWeight: 600, marginTop: 2 }}>
                {memory.process_rss_mb} MB
              </div>
            </Card>
          </Card>
        </Col>

        {/* ===== CPU / 运行时间 ===== */}
        <Col xs={24} md={12} lg={8}>
          <Card
            title={<span><ThunderboltOutlined style={{ marginRight: 6 }} />CPU &amp; 运行</span>}
            style={cardStyle}
          >
            <Progress
              percent={cpu.cpu_pct}
              strokeColor={progressColor(cpu.cpu_pct)}
              format={(p) => `${p}%`}
              style={{ marginBottom: 16 }}
            />
            <Row gutter={12}>
              <Col span={12}>
                <Statistic
                  title={<Text type="secondary" style={{ fontSize: 12 }}>核心数</Text>}
                  value={cpu.cpu_count}
                  suffix="核"
                  valueStyle={{ fontSize: 14 }}
                />
              </Col>
              <Col span={12}>
                <Statistic
                  title={<Text type="secondary" style={{ fontSize: 12 }}>已运行</Text>}
                  value={uptime(cpu.uptime_seconds)}
                  valueStyle={{ fontSize: 14 }}
                />
              </Col>
            </Row>
          </Card>
        </Col>

        {/* ===== 磁盘 / 存储 ===== */}
        <Col xs={24} md={12} lg={8}>
          <Card
            title={<span><HddOutlined style={{ marginRight: 6 }} />磁盘 &amp; 存储</span>}
            style={cardStyle}
          >
            <Progress
              percent={storage.disk_used_pct}
              strokeColor={progressColor(storage.disk_used_pct)}
              format={(p) => `${p}%`}
              style={{ marginBottom: 16 }}
            />
            <Row gutter={12} style={{ marginBottom: 12 }}>
              <Col span={8}>
                <Statistic
                  title={<Text type="secondary" style={{ fontSize: 12 }}>总量</Text>}
                  value={storage.disk_total_gb}
                  suffix="GB"
                  valueStyle={{ fontSize: 14 }}
                />
              </Col>
              <Col span={8}>
                <Statistic
                  title={<Text type="secondary" style={{ fontSize: 12 }}>已用</Text>}
                  value={storage.disk_used_gb}
                  suffix="GB"
                  valueStyle={{ fontSize: 14, color: progressColor(storage.disk_used_pct) }}
                />
              </Col>
              <Col span={8}>
                <Statistic
                  title={<Text type="secondary" style={{ fontSize: 12 }}>剩余</Text>}
                  value={storage.disk_free_gb}
                  suffix="GB"
                  valueStyle={{ fontSize: 14 }}
                />
              </Col>
            </Row>
            <Row gutter={12}>
              {storage.db_size_mb !== null && (
                <Col span={12}>
                  <Card size="small" style={innerCardStyle}>
                    <Text type="secondary" style={{ fontSize: 12 }}>数据库文件</Text>
                    <div style={{ fontSize: 16, fontWeight: 600, marginTop: 2 }}>
                      {storage.db_size_mb} MB
                    </div>
                  </Card>
                </Col>
              )}
              <Col span={storage.db_size_mb !== null ? 12 : 24}>
                <Card size="small" style={innerCardStyle}>
                  <Text type="secondary" style={{ fontSize: 12 }}>媒体文件</Text>
                  <div style={{ fontSize: 16, fontWeight: 600, marginTop: 2 }}>
                    {storage.storage_size_mb} MB
                  </div>
                </Card>
              </Col>
            </Row>
          </Card>
        </Col>

        {/* ===== 数据库记录数 ===== */}
        <Col xs={24} md={14}>
          <Card
            title={<span><DatabaseOutlined style={{ marginRight: 6 }} />数据库记录数</span>}
            style={cardStyle}
          >
            <Row gutter={[12, 12]}>
              {dbRows.map((row) => (
                <Col xs={12} sm={8} md={8} key={row.key}>
                  <Card size="small" style={innerCardStyle}>
                    <Text type="secondary" style={{ fontSize: 12 }}>{row.label}</Text>
                    <div style={{ fontSize: 20, fontWeight: 700, marginTop: 4 }}>
                      {(row.value ?? 0).toLocaleString()}
                    </div>
                  </Card>
                </Col>
              ))}
            </Row>
          </Card>
        </Col>

        {/* ===== 任务状态 ===== */}
        <Col xs={24} md={10}>
          <Card
            title={<span><CloudServerOutlined style={{ marginRight: 6 }} />任务状态分布</span>}
            style={cardStyle}
          >
            {taskRows.length === 0 ? (
              <Text type="secondary">暂无任务记录</Text>
            ) : (
              <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                {taskRows.map((row) => {
                  const colorMap: Record<string, string> = {
                    completed: "success",
                    running: "processing",
                    failed: "error",
                    pending: "warning",
                  };
                  return (
                    <div
                      key={row.status}
                      style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}
                    >
                      <Tag color={colorMap[row.status] ?? "default"} style={{ margin: 0 }}>
                        {row.status}
                      </Tag>
                      <Text strong>{(row.count as number).toLocaleString()}</Text>
                    </div>
                  );
                })}
              </div>
            )}

            <div style={{ marginTop: 16, paddingTop: 12, borderTop: "1px solid #303030" }}>
              <div style={{ display: "flex", justifyContent: "space-between" }}>
                <Text type="secondary" style={{ fontSize: 12 }}>任务总计</Text>
                <Text strong>{(database.tasks_total ?? 0).toLocaleString()}</Text>
              </div>
            </div>
          </Card>
        </Col>
        {/* ===== 网络流量 ===== */}
        <Col xs={24} md={14}>
          <Card
            title={<span><WifiOutlined style={{ marginRight: 6 }} />网络流量</span>}
            style={cardStyle}
          >
            {/* 实时速率 */}
            <Row gutter={12} style={{ marginBottom: 16 }}>
              <Col span={12}>
                <Card size="small" style={{ ...innerCardStyle, borderLeft: "3px solid #22c55e" }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 2 }}>
                    <ArrowDownOutlined style={{ color: "#22c55e", fontSize: 12 }} />
                    <Text type="secondary" style={{ fontSize: 12 }}>下行速率</Text>
                  </div>
                  <div style={{ fontSize: 20, fontWeight: 700, color: "#22c55e" }}>
                    {fmtRate(network.recv_rate_kbps)}
                  </div>
                </Card>
              </Col>
              <Col span={12}>
                <Card size="small" style={{ ...innerCardStyle, borderLeft: "3px solid #3b82f6" }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 2 }}>
                    <ArrowUpOutlined style={{ color: "#3b82f6", fontSize: 12 }} />
                    <Text type="secondary" style={{ fontSize: 12 }}>上行速率</Text>
                  </div>
                  <div style={{ fontSize: 20, fontWeight: 700, color: "#3b82f6" }}>
                    {fmtRate(network.send_rate_kbps)}
                  </div>
                </Card>
              </Col>
            </Row>

            {/* 累计流量 */}
            <Row gutter={12} style={{ marginBottom: 16 }}>
              <Col span={8}>
                <Statistic
                  title={<Text type="secondary" style={{ fontSize: 12 }}>累计下行</Text>}
                  value={network.recv_total_mb}
                  suffix="MB"
                  valueStyle={{ fontSize: 13 }}
                />
              </Col>
              <Col span={8}>
                <Statistic
                  title={<Text type="secondary" style={{ fontSize: 12 }}>累计上行</Text>}
                  value={network.sent_total_mb}
                  suffix="MB"
                  valueStyle={{ fontSize: 13 }}
                />
              </Col>
              <Col span={8}>
                <Statistic
                  title={<Text type="secondary" style={{ fontSize: 12 }}>活跃连接</Text>}
                  value={network.connections >= 0 ? network.connections : "-"}
                  valueStyle={{ fontSize: 13 }}
                />
              </Col>
            </Row>

            {/* 包/错误/丢包 */}
            <Row gutter={12}>
              <Col span={6}>
                <Statistic
                  title={<Text type="secondary" style={{ fontSize: 11 }}>收包</Text>}
                  value={fmtNum(network.packets_recv)}
                  valueStyle={{ fontSize: 13 }}
                />
              </Col>
              <Col span={6}>
                <Statistic
                  title={<Text type="secondary" style={{ fontSize: 11 }}>发包</Text>}
                  value={fmtNum(network.packets_sent)}
                  valueStyle={{ fontSize: 13 }}
                />
              </Col>
              <Col span={6}>
                <Statistic
                  title={<Text type="secondary" style={{ fontSize: 11 }}>错误</Text>}
                  value={network.errin + network.errout}
                  valueStyle={{ fontSize: 13, color: (network.errin + network.errout) > 0 ? "#f59e0b" : undefined }}
                />
              </Col>
              <Col span={6}>
                <Statistic
                  title={<Text type="secondary" style={{ fontSize: 11 }}>丢包</Text>}
                  value={network.dropin + network.dropout}
                  valueStyle={{ fontSize: 13, color: (network.dropin + network.dropout) > 0 ? "#ef4444" : undefined }}
                />
              </Col>
            </Row>
          </Card>
        </Col>

        {/* ===== 网卡列表 ===== */}
        <Col xs={24} md={10}>
          <Card
            title={<span><ApiOutlined style={{ marginRight: 6 }} />网络接口</span>}
            style={cardStyle}
          >
            {network.interfaces.length === 0 ? (
              <Text type="secondary">无可用网卡</Text>
            ) : (
              <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                {network.interfaces.map((nic) => (
                  <Card key={nic.name} size="small" style={innerCardStyle}>
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 4 }}>
                      <Text strong style={{ fontSize: 13 }}>{nic.name}</Text>
                      <Tag color={nic.is_up ? "success" : "default"} style={{ margin: 0 }}>
                        {nic.is_up ? "在线" : "离线"}
                      </Tag>
                    </div>
                    <div style={{ display: "flex", justifyContent: "space-between" }}>
                      <Text type="secondary" style={{ fontSize: 12 }}>{nic.ipv4 || "无 IP"}</Text>
                      {nic.speed > 0 && (
                        <Text type="secondary" style={{ fontSize: 12 }}>{nic.speed} Mbps</Text>
                      )}
                    </div>
                  </Card>
                ))}
              </div>
            )}
          </Card>
        </Col>
      </Row>
    </div>
  );
}
