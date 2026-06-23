import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { Alert } from "../Alert";

// ── Alert 组件单元测试 ──

describe("Alert 组件", () => {
  it("渲染消息内容", () => {
    render(<Alert>这是一条提示信息</Alert>);
    expect(screen.getByText("这是一条提示信息")).toBeInTheDocument();
  });

  it("具有 alert ARIA 角色", () => {
    render(<Alert>提示</Alert>);
    expect(screen.getByRole("alert")).toBeInTheDocument();
  });

  it("默认 type 为 info", () => {
    render(<Alert>默认提示</Alert>);
    const alert = screen.getByRole("alert");
    // info type 使用 var(--info) 颜色
    expect(alert.className).toContain("alert-info");
  });

  it("支持 info type", () => {
    render(<Alert type="info">信息提示</Alert>);
    const alert = screen.getByRole("alert");
    expect(alert.className).toContain("alert-info");
    // info 背景使用 var(--info-bg)
    expect(alert.style.background).toBe("var(--info-bg)");
  });

  it("支持 success type", () => {
    render(<Alert type="success">操作成功</Alert>);
    const alert = screen.getByRole("alert");
    expect(alert.className).toContain("alert-success");
    expect(alert.style.background).toBe("var(--success-bg)");
  });

  it("支持 warning type", () => {
    render(<Alert type="warning">警告信息</Alert>);
    const alert = screen.getByRole("alert");
    expect(alert.className).toContain("alert-warning");
    expect(alert.style.background).toBe("var(--warning-bg)");
  });

  it("支持 error type", () => {
    render(<Alert type="error">错误信息</Alert>);
    const alert = screen.getByRole("alert");
    expect(alert.className).toContain("alert-error");
    expect(alert.style.background).toBe("var(--error-bg)");
  });

  it("渲染为 div 元素", () => {
    render(<Alert>提示</Alert>);
    const alert = screen.getByRole("alert");
    expect(alert.tagName).toBe("DIV");
  });

  it("包含状态指示点（alert-dot）", () => {
    render(<Alert>带指示点的提示</Alert>);
    const alert = screen.getByRole("alert");
    const dot = alert.querySelector(".alert-dot");
    expect(dot).toBeInTheDocument();
  });

  it("支持自定义 className", () => {
    render(<Alert className="my-alert">自定义样式</Alert>);
    const alert = screen.getByRole("alert");
    expect(alert.className).toContain("my-alert");
  });

  it("支持渲染嵌套元素作为 children", () => {
    render(
      <Alert>
        <strong>重要：</strong>
        <span>请仔细阅读</span>
      </Alert>
    );
    expect(screen.getByText("重要：")).toBeInTheDocument();
    expect(screen.getByText("请仔细阅读")).toBeInTheDocument();
  });

  it("info type 的指示点使用 info 颜色", () => {
    render(<Alert type="info">信息</Alert>);
    const alert = screen.getByRole("alert");
    const dot = alert.querySelector(".alert-dot") as HTMLElement;
    expect(dot.style.background).toBe("var(--info)");
  });

  it("error type 的指示点使用 error 颜色", () => {
    render(<Alert type="error">错误</Alert>);
    const alert = screen.getByRole("alert");
    const dot = alert.querySelector(".alert-dot") as HTMLElement;
    expect(dot.style.background).toBe("var(--error)");
  });
});
