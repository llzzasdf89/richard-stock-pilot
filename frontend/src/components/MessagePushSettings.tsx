import { useEffect, useRef, useState } from "react";
import { Alert, App as AntdApp, Button, Card, Form, Skeleton, Slider } from "antd";
import {
  fetchMessagePushSettings,
  saveMessagePushSettings,
  type MessagePushSettings as MessagePushSettingsData
} from "../api";
import {
  AVG_VOLUME_SPEC,
  MARKET_CAP_SPEC,
  PUSH_INTERVAL_SPEC,
  formatLargeMoney,
  formatPushInterval,
  formatVolume
} from "../filterSpecifications";
import type { ScreeningStatus } from "./ScreeningWorkspace";

interface MessagePushSettingsProps {
  onStatusChange?: (status: ScreeningStatus) => void;
}

export default function MessagePushSettings({
  onStatusChange
}: MessagePushSettingsProps) {
  const { message } = AntdApp.useApp();
  const [saved, setSaved] = useState<MessagePushSettingsData | null>(null);
  const [draft, setDraft] = useState<MessagePushSettingsData | null>(null);
  const [loading, setLoading] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);
  const mounted = useRef(false);
  const loadSequence = useRef(0);

  useEffect(() => {
    mounted.current = true;
    void loadSettings();
    return () => {
      mounted.current = false;
      loadSequence.current += 1;
    };
  }, []);

  const dirty =
    saved !== null &&
    draft !== null &&
    (draft.interval_minutes !== saved.interval_minutes ||
      draft.min_market_cap !== saved.min_market_cap ||
      draft.min_avg_volume !== saved.min_avg_volume);

  async function loadSettings() {
    const sequence = ++loadSequence.current;
    setLoading(true);
    setSaved(null);
    setDraft(null);
    setLoadError(null);
    setSaveError(null);
    onStatusChange?.({ loading: true, meta: "正在加载后台消息设置" });

    try {
      const settings = await fetchMessagePushSettings();
      if (!mounted.current || sequence !== loadSequence.current) return;
      setSaved(settings);
      setDraft(settings);
      onStatusChange?.({ loading: false, meta: "后台消息设置已加载" });
    } catch (error) {
      if (!mounted.current || sequence !== loadSequence.current) return;
      setLoadError((error as Error).message);
      onStatusChange?.({ loading: false, meta: "配置读取失败" });
    } finally {
      if (mounted.current && sequence === loadSequence.current) {
        setLoading(false);
      }
    }
  }

  async function saveSettings() {
    if (!draft || !dirty) return;

    const submittedDraft = {
      interval_minutes: draft.interval_minutes,
      min_market_cap: draft.min_market_cap,
      min_avg_volume: draft.min_avg_volume
    };
    setLoading(true);
    setSaveError(null);
    onStatusChange?.({ loading: true, meta: "正在保存后台消息设置" });

    try {
      const settings = await saveMessagePushSettings(submittedDraft);
      if (!mounted.current) return;
      setSaved(settings);
      setDraft(settings);
      onStatusChange?.({ loading: false, meta: "后台消息设置已保存" });
      message.success("设置已保存，将从下一个固定钟点生效");
    } catch (error) {
      if (!mounted.current) return;
      setSaveError((error as Error).message);
      onStatusChange?.({ loading: false, meta: "配置保存失败" });
    } finally {
      if (mounted.current) setLoading(false);
    }
  }

  function updateDraft(changes: Partial<MessagePushSettingsData>) {
    setDraft((current) => (current ? { ...current, ...changes } : current));
    setSaveError(null);
  }

  return (
    <section className="message-push-settings">
      <Card title="后台消息设置">
        {loading && draft === null && <Skeleton active paragraph={{ rows: 4 }} />}

        {loadError && draft === null && (
          <Alert
            type="error"
            showIcon
            title="配置读取失败"
            description={loadError}
            action={
              <Button size="small" onClick={() => void loadSettings()}>
                重试
              </Button>
            }
          />
        )}

        {draft && (
          <>
            {saveError && (
              <Alert
                className="settings-error"
                type="error"
                showIcon
                title="配置保存失败"
                description={saveError}
              />
            )}

            <Form layout="vertical" disabled={loading} onFinish={() => void saveSettings()}>
              <Form.Item label="推送间隔">
                <div className="settings-control">
                  <strong className="settings-value">
                    {formatPushInterval(draft.interval_minutes)}
                  </strong>
                  <Slider
                    ariaLabelForHandle="推送间隔"
                    min={PUSH_INTERVAL_SPEC.min}
                    max={PUSH_INTERVAL_SPEC.max}
                    step={PUSH_INTERVAL_SPEC.step}
                    value={draft.interval_minutes}
                    disabled={loading}
                    tooltip={{
                      formatter: (value) =>
                        value === undefined ? "" : formatPushInterval(value)
                    }}
                    onChange={(interval_minutes) => updateDraft({ interval_minutes })}
                  />
                </div>
              </Form.Item>

              <Form.Item label="最低市值">
                <div className="settings-control">
                  <strong className="settings-value">
                    {formatLargeMoney(draft.min_market_cap)}
                  </strong>
                  <Slider
                    ariaLabelForHandle="最低市值"
                    min={MARKET_CAP_SPEC.min}
                    max={MARKET_CAP_SPEC.max}
                    step={MARKET_CAP_SPEC.step}
                    value={draft.min_market_cap}
                    disabled={loading}
                    tooltip={{
                      formatter: (value) =>
                        value === undefined ? "" : formatLargeMoney(value)
                    }}
                    onChange={(min_market_cap) => updateDraft({ min_market_cap })}
                  />
                </div>
              </Form.Item>

              <Form.Item label="最低月均成交量">
                <div className="settings-control">
                  <strong className="settings-value">
                    {formatVolume(draft.min_avg_volume)}
                  </strong>
                  <Slider
                    ariaLabelForHandle="最低月均成交量"
                    min={AVG_VOLUME_SPEC.min}
                    max={AVG_VOLUME_SPEC.max}
                    step={AVG_VOLUME_SPEC.step}
                    value={draft.min_avg_volume}
                    disabled={loading}
                    tooltip={{
                      formatter: (value) =>
                        value === undefined ? "" : formatVolume(value)
                    }}
                    onChange={(min_avg_volume) => updateDraft({ min_avg_volume })}
                  />
                </div>
              </Form.Item>

              <Button type="primary" htmlType="submit" loading={loading} disabled={!dirty}>
                保存设置
              </Button>
            </Form>
          </>
        )}
      </Card>
    </section>
  );
}
