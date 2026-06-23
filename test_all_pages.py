"""
Aureon 全面功能测试脚本
测试所有页面和功能
"""
from playwright.sync_api import sync_playwright
import json
import time

PRODUCTION_URL = "https://aureon-production-659a.up.railway.app"

class AureonTester:
    def __init__(self):
        self.results = {
            "login": {"status": "pending", "tests": []},
            "dashboard": {"status": "pending", "tests": []},
            "search": {"status": "pending", "tests": []},
            "documents": {"status": "pending", "tests": []},
            "admin": {"status": "pending", "tests": []},
            "analytics": {"status": "pending", "tests": []},
            "support": {"status": "pending", "tests": []},
            "responsive": {"status": "pending", "tests": []},
            "errors": [],
            "summary": {}
        }
        self.page = None
        self.browser = None
        self.context = None

    def log(self, category, test_name, status, message=""):
        """记录测试结果"""
        result = {
            "test": test_name,
            "status": status,
            "message": message,
            "timestamp": time.strftime("%H:%M:%S")
        }
        self.results[category]["tests"].append(result)
        icon = "✅" if status == "PASS" else "❌" if status == "FAIL" else "⚠️"
        print(f"  {icon} {test_name}: {message}" if message else f"  {icon} {test_name}")

    def setup(self):
        """初始化浏览器"""
        self.playwright = sync_playwright().start()
        self.browser = self.playwright.chromium.launch(headless=True)
        self.context = self.browser.new_context(viewport={"width": 1280, "height": 720})
        self.page = self.context.new_page()
        # 收集控制台错误
        self.console_errors = []
        self.page.on("console", lambda msg: self.console_errors.append(msg.text) if msg.type == "error" else None)

    def teardown(self):
        """清理浏览器"""
        if self.browser:
            self.browser.close()
        if self.playwright:
            self.playwright.stop()

    def test_login(self):
        """测试登录页面"""
        print("\n=== 1. 登录页面测试 ===")
        self.results["login"]["status"] = "running"

        try:
            self.page.goto(f"{PRODUCTION_URL}/login")
            self.page.wait_for_load_state("networkidle")
            self.page.wait_for_timeout(1000)

            # 1.1 页面加载
            title = self.page.title()
            if "Aureon" in title:
                self.log("login", "页面加载", "PASS", f"标题: {title}")
            else:
                self.log("login", "页面加载", "FAIL", f"标题异常: {title}")

            # 1.2 登录表单元素
            email_input = self.page.locator('input[type="email"]')
            password_input = self.page.locator('input[type="password"]')
            if email_input.is_visible() and password_input.is_visible():
                self.log("login", "登录表单", "PASS", "邮箱和密码输入框可见")
            else:
                self.log("login", "登录表单", "FAIL", "表单元素缺失")

            # 1.3 演示登录按钮
            demo_btn = self.page.locator('button:has-text("使用演示账号登录")')
            if demo_btn.is_visible():
                self.log("login", "演示登录按钮", "PASS", "按钮可见")
            else:
                self.log("login", "演示登录按钮", "FAIL", "按钮不可见")

            # 1.4 语言切换
            lang_btn = self.page.locator('button:has-text("EN")')
            if lang_btn.is_visible():
                self.log("login", "语言切换", "PASS", "语言切换按钮可见")
            else:
                self.log("login", "语言切换", "FAIL", "语言切换按钮不可见")

            # 1.5 执行登录
            demo_btn.click()
            self.page.wait_for_url("**/dashboard", timeout=10000)
            if "/dashboard" in self.page.url:
                self.log("login", "演示登录", "PASS", "成功跳转到仪表盘")
            else:
                self.log("login", "演示登录", "FAIL", f"跳转失败: {self.page.url}")

            self.results["login"]["status"] = "PASS"

        except Exception as e:
            self.log("login", "登录测试异常", "FAIL", str(e)[:100])
            self.results["login"]["status"] = "FAIL"
            self.results["errors"].append(f"Login: {str(e)[:100]}")

    def test_dashboard(self):
        """测试仪表盘页面"""
        print("\n=== 2. 仪表盘页面测试 ===")
        self.results["dashboard"]["status"] = "running"

        try:
            self.page.goto(f"{PRODUCTION_URL}/dashboard")
            self.page.wait_for_load_state("networkidle")
            self.page.wait_for_timeout(2000)

            # 2.1 页面加载
            if "/dashboard" in self.page.url:
                self.log("dashboard", "页面加载", "PASS")
            else:
                self.log("dashboard", "页面加载", "FAIL", f"URL: {self.page.url}")

            # 2.2 Golden Signals 显示
            golden_signals = self.page.locator('text=延迟, text=流量, text=错误, text=饱和度')
            stats_cards = self.page.locator('[class*="card"], [class*="Card"]')
            if stats_cards.count() > 0:
                self.log("dashboard", "统计卡片", "PASS", f"显示 {stats_cards.count()} 个卡片")
            else:
                self.log("dashboard", "统计卡片", "FAIL", "未找到统计卡片")

            # 2.3 RAG 流水线显示
            pipeline = self.page.locator('text=检索, text=生成')
            if pipeline.count() > 0:
                self.log("dashboard", "RAG 流水线", "PASS", "流水线数据可见")
            else:
                self.log("dashboard", "RAG 流水线", "WARN", "流水线数据未显示")

            # 2.4 图表显示
            charts = self.page.locator('canvas, svg[class*="chart"], [class*="recharts"]')
            if charts.count() > 0:
                self.log("dashboard", "图表显示", "PASS", f"显示 {charts.count()} 个图表")
            else:
                self.log("dashboard", "图表显示", "WARN", "未检测到图表元素")

            # 2.5 系统健康状态
            health_indicators = self.page.locator('[class*="status"], [class*="health"], [class*="indicator"]')
            if health_indicators.count() > 0:
                self.log("dashboard", "系统健康状态", "PASS", f"显示 {health_indicators.count()} 个状态指示器")
            else:
                self.log("dashboard", "系统健康状态", "WARN", "未找到状态指示器")

            # 2.6 侧边栏导航
            sidebar = self.page.locator('nav, [class*="sidebar"], [class*="Sidebar"]')
            if sidebar.count() > 0:
                self.log("dashboard", "侧边栏导航", "PASS", "侧边栏可见")
            else:
                self.log("dashboard", "侧边栏导航", "FAIL", "侧边栏不可见")

            self.results["dashboard"]["status"] = "PASS"

        except Exception as e:
            self.log("dashboard", "仪表盘测试异常", "FAIL", str(e)[:100])
            self.results["dashboard"]["status"] = "FAIL"
            self.results["errors"].append(f"Dashboard: {str(e)[:100]}")

    def test_search(self):
        """测试搜索页面"""
        print("\n=== 3. 搜索页面测试 ===")
        self.results["search"]["status"] = "running"

        try:
            self.page.goto(f"{PRODUCTION_URL}/search")
            self.page.wait_for_load_state("networkidle")
            self.page.wait_for_timeout(1000)

            # 3.1 页面加载
            title = self.page.locator('h1')
            if title.is_visible():
                self.log("search", "页面加载", "PASS", f"标题: {title.text_content()[:30]}")
            else:
                self.log("search", "页面加载", "FAIL", "标题不可见")

            # 3.2 搜索框
            search_input = self.page.locator('input[placeholder*="搜索"]')
            if search_input.is_visible():
                self.log("search", "搜索框", "PASS", "搜索框可见")
            else:
                self.log("search", "搜索框", "FAIL", "搜索框不可见")

            # 3.3 建议按钮居中
            suggestions = self.page.locator('.flex.flex-wrap.justify-center')
            if suggestions.count() > 0:
                self.log("search", "建议按钮居中", "PASS", "使用 justify-center")
            else:
                self.log("search", "建议按钮居中", "WARN", "未找到建议按钮")

            # 3.4 执行搜索
            search_input.fill("Aureon 平台功能介绍")
            self.page.keyboard.press("Enter")
            self.page.wait_for_timeout(5000)

            # 3.5 搜索结果
            answer = self.page.locator('.prose')
            if answer.count() > 0 and len(answer.text_content()) > 50:
                self.log("search", "搜索结果", "PASS", f"返回 {len(answer.text_content())} 字符答案")
            else:
                self.log("search", "搜索结果", "FAIL", "未返回有效答案")

            # 3.6 来源引用
            sources = self.page.locator('text=来源')
            if sources.count() > 0:
                self.log("search", "来源引用", "PASS", "来源区域可见")
            else:
                self.log("search", "来源引用", "WARN", "来源区域不可见")

            # 3.7 字符计数
            char_count = self.page.locator('text=/\\d+\\/1000/')
            if char_count.count() > 0:
                self.log("search", "字符计数", "PASS", "显示字符计数")
            else:
                self.log("search", "字符计数", "WARN", "字符计数不可见")

            self.results["search"]["status"] = "PASS"

        except Exception as e:
            self.log("search", "搜索测试异常", "FAIL", str(e)[:100])
            self.results["search"]["status"] = "FAIL"
            self.results["errors"].append(f"Search: {str(e)[:100]}")

    def test_documents(self):
        """测试文档管理页面"""
        print("\n=== 4. 文档管理页面测试 ===")
        self.results["documents"]["status"] = "running"

        try:
            self.page.goto(f"{PRODUCTION_URL}/documents")
            self.page.wait_for_load_state("networkidle")
            self.page.wait_for_timeout(2000)

            # 4.1 页面加载
            if "/documents" in self.page.url:
                self.log("documents", "页面加载", "PASS")
            else:
                self.log("documents", "页面加载", "FAIL", f"URL: {self.page.url}")

            # 4.2 文档列表
            doc_list = self.page.locator('table, [class*="list"], [class*="grid"]')
            if doc_list.count() > 0:
                self.log("documents", "文档列表", "PASS", "文档列表可见")
            else:
                self.log("documents", "文档列表", "WARN", "文档列表不可见")

            # 4.3 上传按钮
            upload_btn = self.page.locator('button:has-text("上传"), button:has-text("Upload")')
            if upload_btn.count() > 0:
                self.log("documents", "上传按钮", "PASS", "上传按钮可见")
            else:
                self.log("documents", "上传按钮", "WARN", "上传按钮不可见")

            # 4.4 删除按钮
            delete_btn = self.page.locator('button:has-text("删除"), button:has-text("Delete"), [class*="trash"], [class*="delete"]')
            if delete_btn.count() > 0:
                self.log("documents", "删除按钮", "PASS", f"找到 {delete_btn.count()} 个删除按钮")
            else:
                self.log("documents", "删除按钮", "WARN", "删除按钮不可见")

            # 4.5 搜索/筛选
            search_filter = self.page.locator('input[placeholder*="搜索"], input[placeholder*="filter"]')
            if search_filter.count() > 0:
                self.log("documents", "搜索筛选", "PASS", "搜索筛选框可见")
            else:
                self.log("documents", "搜索筛选", "WARN", "搜索筛选框不可见")

            self.results["documents"]["status"] = "PASS"

        except Exception as e:
            self.log("documents", "文档测试异常", "FAIL", str(e)[:100])
            self.results["documents"]["status"] = "FAIL"
            self.results["errors"].append(f"Documents: {str(e)[:100]}")

    def test_admin(self):
        """测试管理页面"""
        print("\n=== 5. 管理页面测试 ===")
        self.results["admin"]["status"] = "running"

        try:
            self.page.goto(f"{PRODUCTION_URL}/admin")
            self.page.wait_for_load_state("networkidle")
            self.page.wait_for_timeout(2000)

            # 5.1 页面加载
            if "/admin" in self.page.url:
                self.log("admin", "页面加载", "PASS")
            else:
                self.log("admin", "页面加载", "FAIL", f"URL: {self.page.url}")

            # 5.2 标签页
            tabs = self.page.locator('[role="tab"], button:has-text("总览"), button:has-text("用户")')
            if tabs.count() > 0:
                self.log("admin", "标签页", "PASS", f"找到 {tabs.count()} 个标签")
            else:
                self.log("admin", "标签页", "FAIL", "未找到标签页")

            # 5.3 总览数据
            overview_data = self.page.locator('text=用户, text=文档, text=查询')
            if overview_data.count() > 0:
                self.log("admin", "总览数据", "PASS", "总览数据可见")
            else:
                self.log("admin", "总览数据", "WARN", "总览数据不可见")

            # 5.4 切换到用户管理
            users_tab = self.page.locator('button:has-text("用户管理"), button:has-text("用户")')
            if users_tab.count() > 0:
                users_tab.first.click()
                self.page.wait_for_timeout(1000)
                user_list = self.page.locator('table, [class*="user"]')
                if user_list.count() > 0:
                    self.log("admin", "用户管理", "PASS", "用户列表可见")
                else:
                    self.log("admin", "用户管理", "WARN", "用户列表不可见")
            else:
                self.log("admin", "用户管理", "WARN", "用户管理标签不可见")

            # 5.5 localStorage 缓存
            has_cache = self.page.evaluate('''() => {
                return localStorage.getItem("aureon:admin:overview") !== null ||
                       localStorage.getItem("aureon:admin:users") !== null;
            }''')
            if has_cache:
                self.log("admin", "localStorage 缓存", "PASS", "数据已缓存")
            else:
                self.log("admin", "localStorage 缓存", "WARN", "数据未缓存")

            self.results["admin"]["status"] = "PASS"

        except Exception as e:
            self.log("admin", "管理测试异常", "FAIL", str(e)[:100])
            self.results["admin"]["status"] = "FAIL"
            self.results["errors"].append(f"Admin: {str(e)[:100]}")

    def test_analytics(self):
        """测试分析页面"""
        print("\n=== 6. 分析页面测试 ===")
        self.results["analytics"]["status"] = "running"

        try:
            self.page.goto(f"{PRODUCTION_URL}/analytics")
            self.page.wait_for_load_state("networkidle")
            self.page.wait_for_timeout(2000)

            # 6.1 页面加载
            if "/analytics" in self.page.url:
                self.log("analytics", "页面加载", "PASS")
            else:
                self.log("analytics", "页面加载", "FAIL", f"URL: {self.page.url}")

            # 6.2 Token 统计
            token_stats = self.page.locator('text=Token, text=token, text=消耗')
            if token_stats.count() > 0:
                self.log("analytics", "Token 统计", "PASS", "Token 统计可见")
            else:
                self.log("analytics", "Token 统计", "WARN", "Token 统计不可见")

            # 6.3 时间范围选择
            time_range = self.page.locator('select, button:has-text("7天"), button:has-text("7d")')
            if time_range.count() > 0:
                self.log("analytics", "时间范围选择", "PASS", "时间范围选择器可见")
            else:
                self.log("analytics", "时间范围选择", "WARN", "时间范围选择器不可见")

            # 6.4 图表显示
            charts = self.page.locator('canvas, svg, [class*="chart"]')
            if charts.count() > 0:
                self.log("analytics", "图表显示", "PASS", f"显示 {charts.count()} 个图表")
            else:
                self.log("analytics", "图表显示", "WARN", "未检测到图表")

            # 6.5 缓存命中率
            cache_stats = self.page.locator('text=缓存, text=命中率, text=Cache')
            if cache_stats.count() > 0:
                self.log("analytics", "缓存命中率", "PASS", "缓存统计可见")
            else:
                self.log("analytics", "缓存命中率", "WARN", "缓存统计不可见")

            self.results["analytics"]["status"] = "PASS"

        except Exception as e:
            self.log("analytics", "分析测试异常", "FAIL", str(e)[:100])
            self.results["analytics"]["status"] = "FAIL"
            self.results["errors"].append(f"Analytics: {str(e)[:100]}")

    def test_support(self):
        """测试客服机器人"""
        print("\n=== 7. 客服机器人测试 ===")
        self.results["support"]["status"] = "running"

        try:
            self.page.goto(f"{PRODUCTION_URL}/dashboard")
            self.page.wait_for_load_state("networkidle")
            self.page.wait_for_timeout(5000)  # 等待 WebSocket 连接

            # 7.1 客服按钮
            support_btn = self.page.locator('button.fixed.bottom-6.right-6')
            if support_btn.is_visible():
                self.log("support", "客服按钮", "PASS", "按钮可见")
            else:
                self.log("support", "客服按钮", "FAIL", "按钮不可见")
                self.results["support"]["status"] = "FAIL"
                return

            # 7.2 打开面板
            support_btn.click()
            self.page.wait_for_timeout(1000)
            panel = self.page.locator('[data-testid="support-panel"]')
            if panel.is_visible():
                self.log("support", "打开面板", "PASS", "面板已打开")
            else:
                self.log("support", "打开面板", "FAIL", "面板未打开")

            # 7.3 快捷回复按钮
            quick_replies = self.page.locator('button:has-text("这个平台能做什么"), button:has-text("如何部署"), button:has-text("支持哪些")')
            if quick_replies.count() >= 3:
                self.log("support", "快捷回复", "PASS", f"显示 {quick_replies.count()} 个快捷回复")
            else:
                self.log("support", "快捷回复", "FAIL", f"只显示 {quick_replies.count()} 个快捷回复")

            # 7.4 测试快捷回复
            quick_replies.first.click()
            self.page.wait_for_timeout(10000)  # 等待 RAG 响应

            messages = self.page.locator('[class*="message"], [class*="Message"]')
            if messages.count() > 0:
                last_msg = messages.last.text_content()
                if len(last_msg) > 50:
                    self.log("support", "快捷回复响应", "PASS", f"收到 {len(last_msg)} 字符响应")
                else:
                    self.log("support", "快捷回复响应", "FAIL", f"响应过短: {last_msg[:50]}")
            else:
                self.log("support", "快捷回复响应", "FAIL", "未收到响应")

            # 7.5 测试手动输入
            chat_input = self.page.locator('textarea')
            if chat_input.is_visible():
                chat_input.fill("Aureon 的价格是多少？")
                self.page.keyboard.press("Enter")
                self.page.wait_for_timeout(10000)

                messages = self.page.locator('[class*="message"], [class*="Message"]')
                if messages.count() > 1:
                    self.log("support", "手动输入", "PASS", "收到响应")
                else:
                    self.log("support", "手动输入", "FAIL", "未收到响应")
            else:
                self.log("support", "手动输入", "FAIL", "输入框不可见")

            self.results["support"]["status"] = "PASS"

        except Exception as e:
            self.log("support", "客服测试异常", "FAIL", str(e)[:100])
            self.results["support"]["status"] = "FAIL"
            self.results["errors"].append(f"Support: {str(e)[:100]}")

    def test_responsive(self):
        """测试响应式布局"""
        print("\n=== 8. 响应式布局测试 ===")
        self.results["responsive"]["status"] = "running"

        viewports = [
            {"width": 1920, "height": 1080, "name": "桌面 1080p"},
            {"width": 1366, "height": 768, "name": "笔记本"},
            {"width": 768, "height": 1024, "name": "平板"},
            {"width": 375, "height": 812, "name": "手机"}
        ]

        for vp in viewports:
            try:
                self.page.set_viewport_size({"width": vp["width"], "height": vp["height"]})
                self.page.goto(f"{PRODUCTION_URL}/dashboard")
                self.page.wait_for_load_state("networkidle")
                self.page.wait_for_timeout(1000)

                # 检查页面是否正常显示
                body = self.page.locator('body')
                if body.is_visible():
                    self.log("responsive", f"{vp['name']} ({vp['width']}x{vp['height']})", "PASS", "页面正常显示")
                else:
                    self.log("responsive", f"{vp['name']}", "FAIL", "页面显示异常")

            except Exception as e:
                self.log("responsive", f"{vp['name']}", "FAIL", str(e)[:50])

        # 恢复默认视口
        self.page.set_viewport_size({"width": 1280, "height": 720})
        self.results["responsive"]["status"] = "PASS"

    def test_console_errors(self):
        """检查控制台错误"""
        print("\n=== 9. 控制台错误检查 ===")

        # 过滤掉已知的无害错误
        known_harmless = [
            "fonts.googleapis.com",
            "ERR_CONNECTION_TIMED_OUT",
            "favicon"
        ]

        critical_errors = []
        for error in self.console_errors:
            is_harmless = any(harmless in error for harmless in known_harmless)
            if not is_harmless:
                critical_errors.append(error[:100])

        if len(critical_errors) == 0:
            print(f"  ✅ 无关键 JavaScript 错误 (共 {len(self.console_errors)} 条，已过滤无害错误)")
        else:
            print(f"  ⚠️ 发现 {len(critical_errors)} 条关键错误:")
            for err in critical_errors[:5]:
                print(f"    - {err}")

    def generate_report(self):
        """生成测试报告"""
        print("\n" + "=" * 60)
        print("📊 Aureon 全面测试报告")
        print("=" * 60)

        total_tests = 0
        passed_tests = 0
        failed_tests = 0
        warn_tests = 0

        for category, data in self.results.items():
            if category in ["errors", "summary"]:
                continue
            if isinstance(data, dict) and "tests" in data:
                for test in data["tests"]:
                    total_tests += 1
                    if test["status"] == "PASS":
                        passed_tests += 1
                    elif test["status"] == "FAIL":
                        failed_tests += 1
                    else:
                        warn_tests += 1

        print(f"\n总测试数: {total_tests}")
        print(f"✅ 通过: {passed_tests}")
        print(f"❌ 失败: {failed_tests}")
        print(f"⚠️ 警告: {warn_tests}")

        # 各模块状态
        print("\n模块状态:")
        for category in ["login", "dashboard", "search", "documents", "admin", "analytics", "support", "responsive"]:
            status = self.results.get(category, {}).get("status", "unknown")
            icon = "✅" if status == "PASS" else "❌" if status == "FAIL" else "⚠️"
            print(f"  {icon} {category}: {status}")

        # 错误汇总
        if self.results["errors"]:
            print(f"\n❌ 发现 {len(self.results['errors'])} 个错误:")
            for i, error in enumerate(self.results["errors"], 1):
                print(f"  {i}. {error}")

        # 保存详细结果
        with open("test_all_results.json", "w", encoding="utf-8") as f:
            json.dump(self.results, f, ensure_ascii=False, indent=2)

        print(f"\n📄 详细结果已保存到 test_all_results.json")

    def run_all(self):
        """运行所有测试"""
        print("🚀 开始 Aureon 全面功能测试")
        print("=" * 60)

        self.setup()

        try:
            self.test_login()
            self.test_dashboard()
            self.test_search()
            self.test_documents()
            self.test_admin()
            self.test_analytics()
            self.test_support()
            self.test_responsive()
            self.test_console_errors()
        finally:
            self.generate_report()
            self.teardown()


if __name__ == "__main__":
    tester = AureonTester()
    tester.run_all()
