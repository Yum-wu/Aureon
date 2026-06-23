import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { Badge } from "../Badge";

// ── Badge 组件单元测试 ──

describe("Badge 组件", () => {
  it("渲染文本内容", () => {
    render(<Badge>新功能</Badge>);
    expect(screen.getByText("新功能")).toBeInTheDocument();
  });

  it("渲染数字内容", () => {
    render(<Badge>99+</Badge>);
    expect(screen.getByText("99+")).toBeInTheDocument();
  });

  it("默认 variant 为 default", () => {
    render(<Badge>默认徽章</Badge>);
    const badge = screen.getByText("默认徽章");
    // default variant 会设置 background inline style
    expect(badge).toBeInTheDocument();
    expect(badge.style.background).toBe("var(--surface-inset)");
  });

  it("支持 success variant", () => {
    render(<Badge variant="success">成功</Badge>);
    const badge = screen.getByText("成功");
    // success variant 使用 emerald 色系类名
    expect(badge.className).toContain("text-emerald-600");
    expect(badge.className).toContain("bg-emerald-500/10");
  });

  it("支持 warning variant", () => {
    render(<Badge variant="warning">警告</Badge>);
    const badge = screen.getByText("警告");
    // warning variant 使用 amber 色系类名
    expect(badge.className).toContain("text-amber-600");
    expect(badge.className).toContain("bg-amber-500/10");
  });

  it("支持 error variant", () => {
    render(<Badge variant="error">错误</Badge>);
    const badge = screen.getByText("错误");
    // error variant 使用 red 色系类名
    expect(badge.className).toContain("text-red-600");
    expect(badge.className).toContain("bg-red-500/10");
  });

  it("渲染为 span 元素（内联显示）", () => {
    render(<Badge>徽章</Badge>);
    const badge = screen.getByText("徽章");
    expect(badge.tagName).toBe("SPAN");
  });

  it("包含圆角和边框样式类", () => {
    render(<Badge>样式徽章</Badge>);
    const badge = screen.getByText("样式徽章");
    expect(badge.className).toContain("rounded-full");
    expect(badge.className).toContain("border");
  });

  it("支持渲染嵌套元素作为 children", () => {
    render(
      <Badge>
        <span>嵌套文本</span>
      </Badge>
    );
    expect(screen.getByText("嵌套文本")).toBeInTheDocument();
  });
});
