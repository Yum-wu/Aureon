import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { Button } from "../Button";

// ── Button 组件单元测试 ──

describe("Button 组件", () => {
  it("默认渲染 children 内容", () => {
    render(<Button>点击我</Button>);
    expect(screen.getByRole("button", { name: "点击我" })).toBeInTheDocument();
  });

  it("点击时触发 onClick 回调", () => {
    const handleClick = vi.fn();
    render(<Button onClick={handleClick}>提交</Button>);
    fireEvent.click(screen.getByRole("button", { name: "提交" }));
    expect(handleClick).toHaveBeenCalledTimes(1);
  });

  it("disabled 状态下按钮不可点击", () => {
    const handleClick = vi.fn();
    render(
      <Button onClick={handleClick} disabled>
        禁用
      </Button>
    );
    const button = screen.getByRole("button", { name: "禁用" });
    expect(button).toBeDisabled();
    fireEvent.click(button);
    expect(handleClick).not.toHaveBeenCalled();
  });

  it("支持 primary variant（默认）", () => {
    render(<Button>主要按钮</Button>);
    const button = screen.getByRole("button", { name: "主要按钮" });
    // 默认 variant 为 primary，包含 glow-btn 类名
    expect(button.className).toContain("glow-btn");
  });

  it("支持 secondary variant", () => {
    render(<Button variant="secondary">次要按钮</Button>);
    const button = screen.getByRole("button", { name: "次要按钮" });
    // secondary variant 使用 glow-btn-outline 类名
    expect(button.className).toContain("glow-btn-outline");
  });

  it("支持 ghost variant", () => {
    render(<Button variant="ghost">幽灵按钮</Button>);
    const button = screen.getByRole("button", { name: "幽灵按钮" });
    // ghost variant 包含 hover:bg 样式类
    expect(button.className).toContain("hover:bg");
  });

  it("支持 sm size", () => {
    render(<Button size="sm">小按钮</Button>);
    const button = screen.getByRole("button", { name: "小按钮" });
    expect(button.className).toContain("px-3");
    expect(button.className).toContain("text-sm");
  });

  it("支持 md size（默认）", () => {
    render(<Button>中按钮</Button>);
    const button = screen.getByRole("button", { name: "中按钮" });
    expect(button.className).toContain("px-4");
    expect(button.className).toContain("text-base");
  });

  it("支持 lg size", () => {
    render(<Button size="lg">大按钮</Button>);
    const button = screen.getByRole("button", { name: "大按钮" });
    expect(button.className).toContain("px-6");
    expect(button.className).toContain("text-lg");
  });

  it("支持自定义 className", () => {
    render(<Button className="custom-class">自定义</Button>);
    const button = screen.getByRole("button", { name: "自定义" });
    expect(button.className).toContain("custom-class");
  });

  it("支持透传原生 button 属性（如 type）", () => {
    render(<Button type="submit">提交表单</Button>);
    const button = screen.getByRole("button", { name: "提交表单" });
    expect(button).toHaveAttribute("type", "submit");
  });

  it("支持 aria-label 无障碍属性", () => {
    render(
      <Button aria-label="关闭对话框">
        <span aria-hidden="true">×</span>
      </Button>
    );
    expect(screen.getByRole("button", { name: "关闭对话框" })).toBeInTheDocument();
  });
});
