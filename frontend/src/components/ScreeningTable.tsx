import { Table, Typography, type TableColumnsType } from "antd";
import type {
  ScreeningFilters,
  ScreeningPayload,
  ScreeningRow,
  TabKey
} from "../api";
import { formatLargeMoney, formatVolume } from "../filterSpecifications";

interface ScreeningTableProps {
  data: ScreeningPayload | null;
  filters: ScreeningFilters;
  loading: boolean;
  mode: TabKey;
  onPageChange: (page: number) => void;
}

export default function ScreeningTable({
  data,
  filters,
  loading,
  mode,
  onPageChange
}: ScreeningTableProps) {
  const columns = buildColumns(mode);

  return (
    <Table<ScreeningRow>
      columns={columns}
      dataSource={data?.results ?? []}
      loading={{ spinning: loading, description: "正在加载筛选结果" }}
      locale={{ emptyText: "暂无符合条件的股票" }}
      pagination={{
        current: filters.page,
        pageSize: filters.page_size,
        total: data?.total ?? 0,
        showSizeChanger: false,
        showTotal: (total) => `共 ${total} 条`,
        onChange: onPageChange
      }}
      rowKey={(row) => `${row.symbol}-${row.data_time}`}
      scroll={{ x: 1800 }}
    />
  );
}

function buildColumns(mode: TabKey): TableColumnsType<ScreeningRow> {
  const closeLabel = mode === "daily" ? "收盘价" : "昨日收盘价";
  const columns: TableColumnsType<ScreeningRow> = [
    {
      title: "代码",
      dataIndex: "symbol",
      key: "symbol",
      fixed: "left",
      width: 110,
      render: (value: string) => (
        <Typography.Text className="stock-symbol" strong>
          {value}
        </Typography.Text>
      )
    },
    { title: "名称", dataIndex: "name", key: "name", width: 130 },
    {
      title: "市场",
      dataIndex: "market",
      key: "market",
      width: 75,
      render: (value: ScreeningRow["market"]) => (value === "US" ? "美股" : "港股")
    },
    { title: "货币", dataIndex: "currency", key: "currency", width: 75 },
    {
      title: "近期财报日期（未来几天内）",
      dataIndex: "earnings_date",
      key: "earnings_date",
      width: 220,
      render: nullableText
    },
    {
      title: closeLabel,
      dataIndex: "close",
      key: "close",
      width: 105,
      align: "right",
      render: formatPrice
    }
  ];

  if (mode === "intraday") {
    columns.push({
      title: "最新价格",
      dataIndex: "latest_price",
      key: "latest_price",
      width: 105,
      align: "right",
      render: formatPrice
    });
  }

  columns.push(
    {
      title: "市值",
      dataIndex: "market_cap",
      key: "market_cap",
      width: 115,
      align: "right",
      render: formatLargeMoney
    },
    {
      title: "月均成交量",
      dataIndex: "avg_volume_1m",
      key: "avg_volume_1m",
      width: 120,
      align: "right",
      render: formatVolume
    },
    {
      title: "BOLL 上轨价格",
      dataIndex: "boll_upper",
      key: "boll_upper",
      width: 135,
      align: "right",
      render: formatPrice
    },
    {
      title: "BOLL 中轨价格",
      dataIndex: "boll_mid",
      key: "boll_mid",
      width: 135,
      align: "right",
      render: formatPrice
    },
    {
      title: "BOLL 下轨价格",
      dataIndex: "boll_lower",
      key: "boll_lower",
      width: 135,
      align: "right",
      render: formatPrice
    },
    {
      title: "MA20均线方向",
      dataIndex: "ma20_direction",
      key: "ma20_direction",
      width: 130,
      render: nullableText
    },
    {
      title: "Z-Score",
      dataIndex: "z_score",
      key: "z_score",
      width: 100,
      align: "right",
      render: formatZScore
    },
    {
      title: "平均波动幅度 ATR14",
      dataIndex: "atr14",
      key: "atr14",
      width: 165,
      align: "right",
      render: formatAtr14
    },
    {
      title: "前10个交易日最低点",
      dataIndex: "previous_10d_low",
      key: "previous_10d_low",
      width: 165,
      align: "right",
      render: formatPrice
    },
    {
      title: "前10个交易日最高点",
      dataIndex: "previous_10d_high",
      key: "previous_10d_high",
      width: 165,
      align: "right",
      render: formatPrice
    },
    {
      title: "是否存在逆转趋势",
      dataIndex: "has_reversal_trend",
      key: "has_reversal_trend",
      width: 145,
      render: nullableText
    },
    {
      title: "是否适合建仓",
      dataIndex: "is_suitable_for_entry",
      key: "is_suitable_for_entry",
      width: 130,
      render: nullableText
    },
    { title: "数据时间", dataIndex: "data_time", key: "data_time", width: 210 }
  );

  return columns;
}

function nullableText(value: string | null) {
  return value ?? "-";
}

function formatPrice(value: number | null) {
  if (value === null) return "-";
  return new Intl.NumberFormat("zh-CN", { maximumFractionDigits: 3 }).format(value);
}

function formatAtr14(value: number | null) {
  if (value === null) return "-";
  return value.toFixed(2);
}

function formatZScore(value: number | null) {
  if (value === null) return "-";
  return value.toFixed(2);
}
