import { useCallback, useState } from "react";
import { Badge, Card, Tabs, Typography } from "antd";
import type { TabKey } from "./api";
import ScreeningWorkspace, {
  type ScreeningStatus
} from "./components/ScreeningWorkspace";

const defaultStatus: Record<TabKey, ScreeningStatus> = {
  daily: { loading: false, meta: "等待日线数据" },
  intraday: { loading: false, meta: "点击按钮刷新分时数据" }
};

function App() {
  const [activeTab, setActiveTab] = useState<TabKey>("daily");
  const [status, setStatus] = useState<ScreeningStatus>(defaultStatus.daily);

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
            { key: "intraday", label: "分时筛选" }
          ]}
          onChange={switchTab}
        />
        <ScreeningWorkspace
          key={activeTab}
          mode={activeTab}
          onStatusChange={handleStatusChange}
        />
      </Card>
    </main>
  );
}

export default App;
