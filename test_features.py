"""
Aureon 功能测试脚本
测试搜索页面对齐、FAQ RAG 搜索、客服机器人功能
"""
from playwright.sync_api import sync_playwright
import json
import time

PRODUCTION_URL = "https://aureon-production-659a.up.railway.app"
DEMO_EMAIL = "demo@aureon.ai"
DEMO_PASSWORD = "demo123456"

def login_demo(page):
    """使用演示账号登录"""
    page.goto(f"{PRODUCTION_URL}/login")
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(1000)

    # 点击演示登录按钮
    demo_btn = page.locator('button:has-text("使用演示账号登录")')
    if demo_btn.is_visible():
        demo_btn.click()
        page.wait_for_url("**/dashboard", timeout=10000)
        print("✅ 演示账号登录成功")
        return True

    # 备用：手动填写表单
    page.locator('input[type="email"]').fill(DEMO_EMAIL)
    page.locator('input[type="password"]').fill(DEMO_PASSWORD)
    page.locator('button[type="submit"]:has-text("登录")').click()
    page.wait_for_url("**/dashboard", timeout=10000)
    print("✅ 手动登录成功")
    return True


def test_search_page_alignment(page):
    """测试搜索页面对齐"""
    print("\n=== 测试 1: 搜索页面对齐 ===")
    errors = []

    page.goto(f"{PRODUCTION_URL}/search")
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(1000)

    # 测试 1.1: 建议按钮居中
    suggestions = page.locator('.flex.flex-wrap.justify-center')
    if suggestions.count() > 0:
        box = suggestions.first.bounding_box()
        viewport = page.viewport_size
        center_x = box['x'] + box['width'] / 2
        viewport_center = viewport['width'] / 2
        offset = abs(center_x - viewport_center)
        if offset < 50:
            print("✅ 1.1 建议按钮居中对齐")
        else:
            errors.append(f"❌ 1.1 建议按钮未居中，偏移 {offset}px")
    else:
        # 检查是否有建议按钮（可能隐藏）
        print("⚠️ 1.1 未找到建议按钮（可能已隐藏）")

    # 测试 1.2: 搜索框居中
    search_input = page.locator('input[placeholder*="搜索"]')
    if search_input.count() > 0:
        box = search_input.first.bounding_box()
        viewport = page.viewport_size
        center_x = box['x'] + box['width'] / 2
        viewport_center = viewport['width'] / 2
        offset = abs(center_x - viewport_center)
        if offset < 50:
            print("✅ 1.2 搜索框居中对齐")
        else:
            errors.append(f"❌ 1.2 搜索框未居中，偏移 {offset}px")

    # 测试 1.3: 标题居中
    title = page.locator('h1')
    if title.count() > 0:
        title_style = title.first.evaluate('el => window.getComputedStyle(el).textAlign')
        if title_style == 'center':
            print("✅ 1.3 标题居中对齐")
        else:
            errors.append(f"❌ 1.3 标题未居中，text-align={title_style}")

    # 测试 1.4: 来源侧边栏空状态
    # 先触发一个搜索
    search_input.fill("测试查询")
    page.keyboard.press("Enter")
    page.wait_for_timeout(3000)

    citation_area = page.locator('text=来源')
    if citation_area.count() > 0:
        print("✅ 1.4 来源侧边栏显示正常")
    else:
        no_sources = page.locator('text=暂无来源引用')
        if no_sources.count() > 0:
            print("✅ 1.4 来源侧边栏空状态显示正确")
        else:
            errors.append("❌ 1.4 来源侧边栏显示异常")

    return errors


def test_rag_faq_search(page):
    """测试 FAQ RAG 搜索准确性"""
    print("\n=== 测试 2: FAQ RAG 搜索 ===")
    errors = []

    test_cases = [
        {
            "query": "Aureon是什么平台？",
            "expected_keywords": ["企业级", "AI", "知识库", "RAG"],
            "expected_source": "aureon-faq-overview",
            "description": "平台概览"
        },
        {
            "query": "如何部署Aureon？",
            "expected_keywords": ["Railway", "Docker", "部署"],
            "expected_source": "aureon-faq-deployment",
            "description": "部署指南"
        },
        {
            "query": "Aureon有哪些API？",
            "expected_keywords": ["API", "端点", "/api/"],
            "expected_source": "aureon-faq-api",
            "description": "API 文档"
        },
        {
            "query": "Aureon支持哪些LLM模型？",
            "expected_keywords": ["Qwen", "GPT", "Claude", "模型"],
            "expected_source": "aureon-faq-overview",
            "description": "模型支持"
        },
        {
            "query": "Aureon性能指标如何？",
            "expected_keywords": ["96.5%", "310ms", "检索"],
            "expected_source": "aureon-faq-overview",
            "description": "性能指标"
        },
        {
            "query": "Aureon的RAG检索是如何工作的？",
            "expected_keywords": ["混合检索", "BM25", "向量", "RRF"],
            "expected_source": "aureon-faq-features",
            "description": "RAG 原理"
        }
    ]

    for i, tc in enumerate(test_cases, 1):
        page.goto(f"{PRODUCTION_URL}/search")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(500)

        # 输入查询
        search_input = page.locator('input[placeholder*="搜索"]')
        search_input.fill(tc["query"])
        page.keyboard.press("Enter")

        # 等待结果
        page.wait_for_timeout(5000)

        # 检查答案区域
        answer_area = page.locator('.prose')
        if answer_area.count() > 0:
            answer_text = answer_area.first.text_content()

            # 检查关键词
            found_keywords = [kw for kw in tc["expected_keywords"] if kw in answer_text]
            if len(found_keywords) >= 2:
                print(f"✅ 2.{i} {tc['description']}: 关键词匹配 {found_keywords}")
            else:
                errors.append(f"❌ 2.{i} {tc['description']}: 关键词不足，找到 {found_keywords}")

            # 检查来源引用
            sources = page.locator('[class*="citation"], [class*="source"]')
            if sources.count() > 0:
                print(f"   来源: {sources.count()} 个引用")
        else:
            errors.append(f"❌ 2.{i} {tc['description']}: 未返回答案")

    return errors


def test_support_widget(page):
    """测试客服机器人功能"""
    print("\n=== 测试 3: 客服机器人 ===")
    errors = []

    page.goto(f"{PRODUCTION_URL}/dashboard")
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(2000)

    # 测试 3.1: 客服按钮存在
    support_btn = page.locator('[class*="support"], [class*="Support"], button:has-text("客服"), button:has-text("帮助")')
    if support_btn.count() == 0:
        # 尝试查找浮动按钮
        support_btn = page.locator('.fixed.bottom-4.right-4 button, .fixed.bottom-6.right-6 button')

    if support_btn.count() > 0:
        print("✅ 3.1 客服按钮存在")
    else:
        errors.append("❌ 3.1 未找到客服按钮")
        return errors

    # 测试 3.2: 点击打开客服面板
    support_btn.first.click()
    page.wait_for_timeout(1000)

    # 检查客服面板是否打开
    chat_panel = page.locator('[class*="chat"], [class*="Chat"], [class*="panel"], [class*="Panel"]')
    if chat_panel.count() > 0:
        print("✅ 3.2 客服面板打开成功")
    else:
        errors.append("❌ 3.2 客服面板未打开")

    # 测试 3.3: 快捷回复按钮
    quick_replies = page.locator('button:has-text("这个平台能做什么"), button:has-text("如何部署"), button:has-text("支持哪些"), button:has-text("性能指标")')
    if quick_replies.count() >= 3:
        print(f"✅ 3.3 快捷回复按钮显示 ({quick_replies.count()} 个)")
    else:
        errors.append(f"❌ 3.3 快捷回复按钮不足 ({quick_replies.count()} 个)")

    # 测试 3.4: 点击快捷回复
    if quick_replies.count() > 0:
        quick_replies.first.click()
        page.wait_for_timeout(3000)

        # 检查是否有回复
        messages = page.locator('[class*="message"], [class*="Message"]')
        if messages.count() > 0:
            last_msg = messages.last.text_content()
            if len(last_msg) > 10:
                print(f"✅ 3.4 客服回复正常 ({len(last_msg)} 字符)")
            else:
                errors.append(f"❌ 3.4 客服回复过短: {last_msg}")
        else:
            errors.append("❌ 3.4 未收到客服回复")

    # 测试 3.5: 手动输入问题
    chat_input = page.locator('textarea, input[type="text"]').last
    if chat_input.is_visible():
        chat_input.fill("Aureon的价格是多少？")
        page.keyboard.press("Enter")
        page.wait_for_timeout(5000)

        messages = page.locator('[class*="message"], [class*="Message"]')
        if messages.count() > 0:
            last_msg = messages.last.text_content()
            if "成本" in last_msg or "价格" in last_msg or "$" in last_msg:
                print("✅ 3.5 手动问答正常")
            else:
                errors.append(f"❌ 3.5 回复内容不相关: {last_msg[:100]}")
        else:
            errors.append("❌ 3.5 未收到回复")

    return errors


def test_search_responsiveness(page):
    """测试搜索页面响应式布局"""
    print("\n=== 测试 4: 响应式布局 ===")
    errors = []

    viewports = [
        {"width": 1920, "height": 1080, "name": "桌面 1080p"},
        {"width": 1366, "height": 768, "name": "笔记本"},
        {"width": 768, "height": 1024, "name": "平板"},
        {"width": 375, "height": 812, "name": "手机"}
    ]

    for vp in viewports:
        page.set_viewport_size({"width": vp["width"], "height": vp["height"]})
        page.goto(f"{PRODUCTION_URL}/search")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(500)

        # 检查搜索框是否可见
        search_input = page.locator('input[placeholder*="搜索"]')
        if search_input.is_visible():
            box = search_input.bounding_box()
            if box['width'] > 100:  # 搜索框应该有合理宽度
                print(f"✅ 4.{viewports.index(vp)+1} {vp['name']}: 搜索框正常 ({int(box['width'])}px)")
            else:
                errors.append(f"❌ 4.{viewports.index(vp)+1} {vp['name']}: 搜索框过窄 ({int(box['width'])}px)")
        else:
            errors.append(f"❌ 4.{viewports.index(vp)+1} {vp['name']}: 搜索框不可见")

    # 恢复默认视口
    page.set_viewport_size({"width": 1280, "height": 720})
    return errors


def test_console_errors(page):
    """检查控制台错误"""
    print("\n=== 测试 5: 控制台错误检查 ===")
    errors = []

    console_messages = []
    page.on("console", lambda msg: console_messages.append({"type": msg.type, "text": msg.text}))

    page.goto(f"{PRODUCTION_URL}/search")
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(2000)

    # 执行搜索触发更多代码路径
    search_input = page.locator('input[placeholder*="搜索"]')
    search_input.fill("测试查询")
    page.keyboard.press("Enter")
    page.wait_for_timeout(3000)

    # 分析控制台消息
    error_msgs = [m for m in console_messages if m["type"] == "error"]
    warning_msgs = [m for m in console_messages if m["type"] == "warning"]

    if len(error_msgs) == 0:
        print("✅ 5.1 无 JavaScript 错误")
    else:
        for msg in error_msgs[:3]:  # 只显示前3个
            errors.append(f"❌ 5.1 JS错误: {msg['text'][:100]}")

    if len(warning_msgs) <= 3:
        print(f"✅ 5.2 警告数量合理 ({len(warning_msgs)} 个)")
    else:
        print(f"⚠️ 5.2 警告较多 ({len(warning_msgs)} 个)")

    return errors


def test_performance(page):
    """测试性能指标"""
    print("\n=== 测试 6: 性能指标 ===")
    errors = []

    # 测试页面加载时间
    start_time = time.time()
    page.goto(f"{PRODUCTION_URL}/search")
    page.wait_for_load_state("networkidle")
    load_time = time.time() - start_time

    if load_time < 3:
        print(f"✅ 6.1 页面加载时间: {load_time:.2f}s")
    elif load_time < 5:
        print(f"⚠️ 6.1 页面加载时间稍慢: {load_time:.2f}s")
    else:
        errors.append(f"❌ 6.1 页面加载时间过慢: {load_time:.2f}s")

    # 测试搜索响应时间
    search_input = page.locator('input[placeholder*="搜索"]')
    search_input.fill("Aureon功能")

    start_time = time.time()
    page.keyboard.press("Enter")
    # 等待答案出现
    page.locator('.prose').wait_for(timeout=15000)
    response_time = time.time() - start_time

    if response_time < 5:
        print(f"✅ 6.2 搜索响应时间: {response_time:.2f}s")
    elif response_time < 10:
        print(f"⚠️ 6.2 搜索响应时间稍慢: {response_time:.2f}s")
    else:
        errors.append(f"❌ 6.2 搜索响应时间过慢: {response_time:.2f}s")

    return errors


def main():
    print("🚀 开始 Aureon 功能测试")
    print("=" * 50)

    all_errors = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1280, "height": 720})
        page = context.new_page()

        # 登录
        try:
            login_demo(page)
        except Exception as e:
            print(f"❌ 登录失败: {e}")
            browser.close()
            return

        # 运行所有测试
        tests = [
            ("搜索页面对齐", test_search_page_alignment),
            ("FAQ RAG 搜索", test_rag_faq_search),
            ("客服机器人", test_support_widget),
            ("响应式布局", test_search_responsiveness),
            ("控制台错误", test_console_errors),
            ("性能指标", test_performance)
        ]

        for test_name, test_func in tests:
            try:
                errors = test_func(page)
                all_errors.extend(errors)
            except Exception as e:
                error_msg = f"❌ {test_name} 测试异常: {str(e)[:100]}"
                print(error_msg)
                all_errors.append(error_msg)

        browser.close()

    # 汇总结果
    print("\n" + "=" * 50)
    print("📊 测试结果汇总")
    print("=" * 50)

    if len(all_errors) == 0:
        print("🎉 所有测试通过！")
    else:
        print(f"⚠️ 发现 {len(all_errors)} 个问题:\n")
        for i, error in enumerate(all_errors, 1):
            print(f"  {i}. {error}")

    # 保存结果到文件
    result = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "total_errors": len(all_errors),
        "errors": all_errors,
        "status": "PASS" if len(all_errors) == 0 else "FAIL"
    }

    with open("test_results.json", "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"\n📄 详细结果已保存到 test_results.json")


if __name__ == "__main__":
    main()
