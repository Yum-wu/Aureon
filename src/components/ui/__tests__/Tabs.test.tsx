import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { Tabs } from "../Tabs";

// ── Tabs 组件单元测试 ──

const TEST_TABS = [
  { id: "overview", label: "概览" },
  { id: "analytics", label: "分析" },
  { id: "settings", label: "设置" },
];

describe("Tabs 组件", () => {
  it("渲染所有 tab 标签", () => {
    render(<Tabs tabs={TEST_TABS} activeTab="overview" onChange={() => {}} />);
    expect(screen.getByText("概览")).toBeInTheDocument();
    expect(screen.getByText("分析")).toBeInTheDocument();
    expect(screen.getByText("设置")).toBeInTheDocument();
  });

  it("具有 tablist ARIA 角色", () => {
    render(<Tabs tabs={TEST_TABS} activeTab="overview" onChange={() => {}} />);
    expect(screen.getByRole("tablist")).toBeInTheDocument();
  });

  it("每个 tab 具有 tab ARIA 角色", () => {
    render(<Tabs tabs={TEST_TABS} activeTab="overview" onChange={() => {}} />);
    const tabs = screen.getAllByRole("tab");
    expect(tabs).toHaveLength(3);
  });

  it("默认激活第一个 tab 时 aria-selected 为 true", () => {
    render(<Tabs tabs={TEST_TABS} activeTab="overview" onChange={() => {}} />);
    const overviewTab = screen.getByRole("tab", { name: "概览" });
    expect(overviewTab).toHaveAttribute("aria-selected", "true");
  });

  it("非激活 tab 的 aria-selected 为 false", () => {
    render(<Tabs tabs={TEST_TABS} activeTab="overview" onChange={() => {}} />);
    const analyticsTab = screen.getByRole("tab", { name: "分析" });
    expect(analyticsTab).toHaveAttribute("aria-selected", "false");
  });

  it("点击 tab 时触发 onChange 回调并传入 tab id", () => {
    const handleChange = vi.fn();
    render(<Tabs tabs={TEST_TABS} activeTab="overview" onChange={handleChange} />);

    fireEvent.click(screen.getByRole("tab", { name: "分析" }));
    expect(handleChange).toHaveBeenCalledWith("analytics");
    expect(handleChange).toHaveBeenCalledTimes(1);
  });

  it("点击不同 tab 都能正确触发 onChange", () => {
    const handleChange = vi.fn();
    render(<Tabs tabs={TEST_TABS} activeTab="overview" onChange={handleChange} />);

    fireEvent.click(screen.getByRole("tab", { name: "设置" }));
    expect(handleChange).toHaveBeenCalledWith("settings");

    fireEvent.click(screen.getByRole("tab", { name: "概览" }));
    expect(handleChange).toHaveBeenCalledWith("overview");

    expect(handleChange).toHaveBeenCalledTimes(2);
  });

  it("激活的 tab 显示下划线指示器", () => {
    render(<Tabs tabs={TEST_TABS} activeTab="analytics" onChange={() => {}} />);
    const activeTab = screen.getByRole("tab", { name: "分析" });
    // 激活 tab 内部包含一个 span 作为下划线指示器
    const indicator = activeTab.querySelector("span");
    expect(indicator).toBeInTheDocument();
  });

  it("非激活的 tab 不显示下划线指示器", () => {
    render(<Tabs tabs={TEST_TABS} activeTab="overview" onChange={() => {}} />);
    const inactiveTab = screen.getByRole("tab", { name: "分析" });
    const indicator = inactiveTab.querySelector("span");
    expect(indicator).not.toBeInTheDocument();
  });

  it("支持自定义 className", () => {
    render(
      <Tabs
        tabs={TEST_TABS}
        activeTab="overview"
        onChange={() => {}}
        className="custom-tabs"
      />
    );
    const tablist = screen.getByRole("tablist");
    expect(tablist.className).toContain("custom-tabs");
  });

  it("支持带 icon 的 tab", () => {
    const tabsWithIcon = [
      { id: "home", label: "首页", icon: <span data-testid="home-icon">🏠</span> },
      { id: "profile", label: "个人" },
    ];
    render(<Tabs tabs={tabsWithIcon} activeTab="home" onChange={() => {}} />);
    expect(screen.getByTestId("home-icon")).toBeInTheDocument();
  });
});
