import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { ProgressBar } from "../ProgressBar";

// ── ProgressBar 组件单元测试 ──

describe("ProgressBar 组件", () => {
  it("渲染 progressbar ARIA 角色", () => {
    render(<ProgressBar value={50} />);
    expect(screen.getByRole("progressbar")).toBeInTheDocument();
  });

  it("设置正确的 aria-valuenow", () => {
    render(<ProgressBar value={75} />);
    const bar = screen.getByRole("progressbar");
    expect(bar).toHaveAttribute("aria-valuenow", "75");
  });

  it("aria-valuemin 默认为 0", () => {
    render(<ProgressBar value={50} />);
    const bar = screen.getByRole("progressbar");
    expect(bar).toHaveAttribute("aria-valuemin", "0");
  });

  it("aria-valuemax 默认为 100", () => {
    render(<ProgressBar value={50} />);
    const bar = screen.getByRole("progressbar");
    expect(bar).toHaveAttribute("aria-valuemax", "100");
  });

  it("value 超过 100 时被限制为 100", () => {
    render(<ProgressBar value={150} />);
    const bar = screen.getByRole("progressbar");
    expect(bar).toHaveAttribute("aria-valuenow", "100");
  });

  it("value 低于 0 时被限制为 0", () => {
    render(<ProgressBar value={-20} />);
    const bar = screen.getByRole("progressbar");
    expect(bar).toHaveAttribute("aria-valuenow", "0");
  });

  it("渲染 label 文本", () => {
    render(<ProgressBar value={50} label="上传进度" />);
    expect(screen.getByText("上传进度")).toBeInTheDocument();
  });

  it("showPercentage=true 时显示百分比文本", () => {
    render(<ProgressBar value={42} showPercentage />);
    expect(screen.getByText("42%")).toBeInTheDocument();
  });

  it("showPercentage 显示四舍五入的百分比", () => {
    render(<ProgressBar value={42.7} showPercentage />);
    expect(screen.getByText("43%")).toBeInTheDocument();
  });

  it("未提供 label 和 showPercentage 时不渲染头部区域", () => {
    render(<ProgressBar value={50} />);
    // 只应有 progressbar 元素，不应有额外文本
    expect(screen.queryByText(/%/)).not.toBeInTheDocument();
  });

  it("支持 brand variant（默认）", () => {
    render(<ProgressBar value={50} />);
    const bar = screen.getByRole("progressbar");
    // 默认 variant 为 brand，内部填充使用 var(--seed-primary)
    const fill = bar.firstChild as HTMLElement;
    expect(fill.style.background).toBe("var(--seed-primary)");
  });

  it("支持 accent variant", () => {
    render(<ProgressBar value={50} variant="accent" />);
    const bar = screen.getByRole("progressbar");
    const fill = bar.firstChild as HTMLElement;
    expect(fill.style.background).toBe("var(--seed-accent)");
  });

  it("支持 success variant", () => {
    render(<ProgressBar value={50} variant="success" />);
    const bar = screen.getByRole("progressbar");
    const fill = bar.firstChild as HTMLElement;
    expect(fill.style.background).toBe("var(--success)");
  });

  it("支持 warning variant", () => {
    render(<ProgressBar value={50} variant="warning" />);
    const bar = screen.getByRole("progressbar");
    const fill = bar.firstChild as HTMLElement;
    expect(fill.style.background).toBe("var(--warning)");
  });

  it("支持 error variant", () => {
    render(<ProgressBar value={50} variant="error" />);
    const bar = screen.getByRole("progressbar");
    const fill = bar.firstChild as HTMLElement;
    expect(fill.style.background).toBe("var(--error)");
  });

  it("填充宽度与 value 百分比一致", () => {
    render(<ProgressBar value={60} />);
    const bar = screen.getByRole("progressbar");
    const fill = bar.firstChild as HTMLElement;
    expect(fill.style.width).toBe("60%");
  });

  it("同时显示 label 和 percentage", () => {
    render(
      <ProgressBar value={80} label="处理中" showPercentage />
    );
    expect(screen.getByText("处理中")).toBeInTheDocument();
    expect(screen.getByText("80%")).toBeInTheDocument();
  });
});
