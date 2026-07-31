import { useCallback, useState } from "react";
import { Badge, Card, Tabs, Typography } from "antd";
import type { TabKey } from "./api";
import MessagePushSettings from "./components/MessagePushSettings";
import ScreeningWorkspace, {
  type ScreeningStatus
} from "./components/ScreeningWorkspace";

const defaultStatus: Record<TabKey, ScreeningStatus> = {
  daily: { loading: false, meta: "等待日线数据" },
  intraday: { loading: false, meta: "点击按钮刷新分时数据" },
  settings: { loading: false, meta: "等待加载后台消息设置" }
};

interface AppProps {
  initialTab?: TabKey;
}

function App({ initialTab = "daily" }: AppProps) {
  const [activeTab, setActiveTab] = useState<TabKey>(initialTab);
  const [status, setStatus] = useState<ScreeningStatus>(defaultStatus[initialTab]);

  const handleStatusChange = useCallback((nextStatus: ScreeningStatus) => {
    setStatus(nextStatus);
  }, []);

  function switchTab(key: string) {
    const nextTab = key as TabKey;
    if (nextTab === activeTab) return;
    setActiveTab(nextTab);
    setStatus(defaultStatus[nextTab]);
  }

  return (
    <main className="app-shell">
      <Card className="topbar">
        <div className="topbar-content">
          <div>
            <Typography.Title level={4}>Richard Stock Pilot</Typography.Title>
            <Typography.Text type="secondary">{status.meta}</Typography.Text>
          </div>
          <Badge
            status={status.loading ? "processing" : "success"}
            text={status.loading ? "请求中" : "就绪"}
          />
        </div>
      </Card>

      <Card className="workspace" styles={{ body: { padding: 0 } }}>
        <Tabs
          className="channel-tabs"
          activeKey={activeTab}
          aria-label="筛选频道"
          items={[
            { key: "daily", label: "日线筛选" },
            { key: "intraday", label: "分时筛选" },
            { key: "settings", label: "后台消息设置" }
          ]}
          onChange={switchTab}
        />
        {activeTab === "settings" ? (
          <MessagePushSettings onStatusChange={handleStatusChange} />
        ) : (
          <ScreeningWorkspace
            key={activeTab}
            mode={activeTab}
            onStatusChange={handleStatusChange}
          />
        )}
      </Card>
    </main>
  );
}

export default App;
