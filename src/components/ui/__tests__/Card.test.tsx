import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { Card } from "../Card";

// ── Card 组件单元测试 ──

describe("Card 组件", () => {
  it("渲染 children 内容", () => {
    render(
      <Card>
        <p>卡片内容</p>
      </Card>
    );
    expect(screen.getByText("卡片内容")).toBeInTheDocument();
  });

  it("渲染复杂的 children 结构", () => {
    render(
      <Card>
        <h2>标题</h2>
        <p>描述文本</p>
        <button>操作按钮</button>
      </Card>
    );
    expect(screen.getByText("标题")).toBeInTheDocument();
    expect(screen.getByText("描述文本")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "操作按钮" })).toBeInTheDocument();
  });

  it("支持自定义 className", () => {
    render(<Card className="my-custom-card">内容</Card>);
    // getByText 返回直接包含文本的元素（即 Card 的根 div）
    const card = screen.getByText("内容");
    expect(card.className).toContain("my-custom-card");
  });

  it("默认 hover 为 false（无 cursor-pointer）", () => {
    render(<Card>静态卡片</Card>);
    const card = screen.getByText("静态卡片");
    // hover=false 时不包含 cursor-pointer 类
    expect(card.className).not.toContain("cursor-pointer");
  });

  it("hover=true 时包含交互样式", () => {
    render(<Card hover>可悬停卡片</Card>);
    const card = screen.getByText("可悬停卡片");
    expect(card.className).toContain("cursor-pointer");
    expect(card.className).toContain("hover:border");
  });

  it("支持透传 onClick 事件", () => {
    const handleClick = vi.fn();
    render(
      <Card onClick={handleClick} hover>
        可点击卡片
      </Card>
    );
    fireEvent.click(screen.getByText("可点击卡片"));
    expect(handleClick).toHaveBeenCalledTimes(1);
  });

  it("支持透传原生 div 属性（如 data-testid）", () => {
    render(<Card data-testid="my-card">内容</Card>);
    expect(screen.getByTestId("my-card")).toBeInTheDocument();
  });

  it("支持透传 title 属性", () => {
    render(
      <Card title="卡片提示">
        <span>带 title 的卡片</span>
      </Card>
    );
    // 当 children 是嵌套元素时，getByText 返回的是子元素，需要用 closest 找到 Card 根元素
    const innerSpan = screen.getByText("带 title 的卡片");
    const card = innerSpan.closest("[title]");
    expect(card).toHaveAttribute("title", "卡片提示");
  });
});
