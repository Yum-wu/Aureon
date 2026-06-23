import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { MetricCard } from "../MetricCard";

// ── MetricCard 组件单元测试 ──

describe("MetricCard 组件", () => {
  it("渲染标题 label 和数值 value", () => {
    render(<MetricCard label="总查询数" value={1234} />);
    expect(screen.getByText("总查询数")).toBeInTheDocument();
    expect(screen.getByText("1234")).toBeInTheDocument();
  });

  it("支持字符串类型的 value", () => {
    render(<MetricCard label="准确率" value="95.2%" />);
    expect(screen.getByText("95.2%")).toBeInTheDocument();
  });

  it("支持数字类型的 value", () => {
    render(<MetricCard label="文档数" value={42} />);
    expect(screen.getByText("42")).toBeInTheDocument();
  });

  it("渲染单位 suffix", () => {
    render(<MetricCard label="延迟" value={50} suffix="ms" />);
    expect(screen.getByText("ms")).toBeInTheDocument();
    expect(screen.getByText("50")).toBeInTheDocument();
  });

  it("未提供 suffix 时不渲染单位", () => {
    render(<MetricCard label="计数" value={10} />);
    expect(screen.getByText("10")).toBeInTheDocument();
    // 不应渲染 "ms" 或其他单位文本
    const card = screen.getByText("计数").parentElement;
    expect(card?.textContent).toBe("计数10");
  });

  it("渲染正向趋势 change（上升）", () => {
    render(<MetricCard label="增长" value={100} change={15} />);
    expect(screen.getByText(/15/)).toBeInTheDocument();
    // 正向 change 显示上升箭头 ↑
    expect(screen.getByText(/↑/)).toBeInTheDocument();
  });

  it("渲染负向趋势 change（下降）", () => {
    render(<MetricCard label="下降" value={100} change={-8} />);
    expect(screen.getByText(/8/)).toBeInTheDocument();
    // 负向 change 显示下降箭头 ↓
    expect(screen.getByText(/↓/)).toBeInTheDocument();
  });

  it("渲染 changeLabel 描述文本", () => {
    render(
      <MetricCard label="查询量" value={500} change={10} changeLabel="较上周" />
    );
    expect(screen.getByText("较上周")).toBeInTheDocument();
  });

  it("未提供 change 时不渲染趋势区域", () => {
    render(<MetricCard label="静态指标" value={100} />);
    // 不应出现箭头符号
    expect(screen.queryByText(/↑/)).not.toBeInTheDocument();
    expect(screen.queryByText(/↓/)).not.toBeInTheDocument();
  });

  it("change 为 0 时显示上升箭头（>=0 判断）", () => {
    // 使用非数字 value 避免 "0" 与 value 中的字符冲突
    render(<MetricCard label="持平" value="N/A" change={0} />);
    // change >= 0 显示 ↑
    expect(screen.getByText(/↑/)).toBeInTheDocument();
    // 验证 change 区域包含 0% 文本
    expect(screen.getByText(/0/)).toBeInTheDocument();
  });

  it("label 转为大写显示（CSS 类）", () => {
    render(<MetricCard label="total" value={100} />);
    const label = screen.getByText("total");
    expect(label.className).toContain("uppercase");
  });
});
