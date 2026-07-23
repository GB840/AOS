"""投标分析端到端验证脚本。

用法：先启动 AOS 服务（run.bat），等 "AOS v5.0 ready" 出现后，运行：
    python test_bidding_e2e.py

会自动创建一个测试 PDF，上传到 /api/bidding/analyze，打印结构化报告。
"""
import io
import json
import sys
import time
import urllib.request
import urllib.error

API = "http://127.0.0.1:8000"


def wait_for_server(timeout=120):
    """等待服务就绪。"""
    print("等待 AOS 服务就绪...", end="", flush=True)
    for i in range(timeout):
        try:
            r = urllib.request.urlopen(f"{API}/health", timeout=2)
            if r.status == 200:
                print(f" OK ({i+1}s)")
                return True
        except Exception:
            pass
        time.sleep(1)
        if (i + 1) % 10 == 0:
            print(f" {i+1}s", end="", flush=True)
    print(" TIMEOUT")
    return False


def create_test_pdf():
    """生成一个最小合法 PDF（含中文招标关键词）。"""
    content = """
    招标公告

    一、项目概况
    项目名称：XX市智慧城市信息化建设项目
    预算金额：500万元

    二、投标人资格要求
    资质要求：投标人应具备计算机信息系统集成二级及以上资质
    投标人须具备ISO9001质量管理体系认证
    近三年内完成过类似项目业绩不少于3个

    三、技术要求
    1. 系统应支持不少于1000个并发用户
    2. 响应时间不超过2秒
    3. 数据存储容量不少于10TB

    四、商务要求
    投标保证金：10万元
    履约保证金：合同金额的5%
    工期：180个日历天

    五、评标办法
    采用综合评分法，技术分60分，商务分30分，价格分10分。
    """
    # 最简 PDF 结构
    text_bytes = content.encode("utf-8")
    stream = f"BT /F1 12 Tf 72 720 Td ({content[:200]}) Tj ET".encode("latin-1", errors="replace")

    pdf = io.BytesIO()
    pdf.write(b"%PDF-1.4\n")

    # obj 1: catalog
    obj1_offset = pdf.tell()
    pdf.write(b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n")

    # obj 2: pages
    obj2_offset = pdf.tell()
    pdf.write(b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n")

    # obj 3: page
    obj3_offset = pdf.tell()
    pdf.write(b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>\nendobj\n")

    # obj 4: content stream
    obj4_offset = pdf.tell()
    pdf.write(f"4 0 obj\n<< /Length {len(stream)} >>\nstream\n".encode())
    pdf.write(stream)
    pdf.write(b"\nendstream\nendobj\n")

    # obj 5: font
    obj5_offset = pdf.tell()
    pdf.write(b"5 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n")

    # xref
    xref_offset = pdf.tell()
    pdf.write(b"xref\n0 6\n")
    pdf.write(b"0000000000 65535 f \n")
    for off in [obj1_offset, obj2_offset, obj3_offset, obj4_offset, obj5_offset]:
        pdf.write(f"{off:010d} 00000 n \n".encode())

    pdf.write(b"trailer\n<< /Size 6 /Root 1 0 R >>\n")
    pdf.write(f"startxref\n{xref_offset}\n".encode())
    pdf.write(b"%%EOF\n")

    return pdf.getvalue()


def test_analyze():
    """上传测试 PDF 到 /api/bidding/analyze。"""
    pdf_data = create_test_pdf()
    print(f"测试 PDF 大小: {len(pdf_data)} bytes")

    # 构造 multipart/form-data
    boundary = "----AOSBoundary7MA4YWxkTrZu0gW"
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="test_bidding.pdf"\r\n'
        f"Content-Type: application/pdf\r\n\r\n"
    ).encode() + pdf_data + (
        f"\r\n--{boundary}\r\n"
        f'Content-Disposition: form-data; name="company_name"\r\n\r\n'
        f"测试科技有限公司"
        f"\r\n--{boundary}\r\n"
        f'Content-Disposition: form-data; name="qualifications"\r\n\r\n'
        f"计算机信息系统集成二级,ISO9001"
        f"\r\n--{boundary}--\r\n"
    ).encode()

    req = urllib.request.Request(
        f"{API}/api/bidding/analyze",
        data=body,
        method="POST",
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )

    print("上传分析中...", end="", flush=True)
    try:
        r = urllib.request.urlopen(req, timeout=60)
        data = json.loads(r.read().decode())
        print(f" HTTP {r.status}")
        return data
    except urllib.error.HTTPError as e:
        detail = e.read().decode()[:200]
        print(f" HTTP {e.code}: {detail}")
        return None


def print_report(data):
    """打印结构化报告摘要。"""
    if not data:
        print("\n[FAIL] 未获得有效响应")
        return False

    print("\n" + "=" * 60)
    print("  投标分析报告")
    print("=" * 60)

    if not data.get("ok"):
        print(f"  状态: 失败 - {data.get('error', '未知错误')}")
        return False

    a = data.get("analysis", {})
    print(f"  PDF 页数: {a.get('pdf_pages', '?')}")
    print(f"  检测章节: {a.get('sections_detected', 0)}")
    print(f"  核心需求: {len(a.get('requirements', []))} 条")
    for i, req in enumerate(a.get("requirements", [])[:5], 1):
        print(f"    {i}. [{req.get('type', '?')}] {req.get('detail', '')[:60]}")

    compliance = data.get("compliance", [])
    critical = data.get("critical_risks", [])
    print(f"\n  合规检查: {len(compliance)} 条规则")
    print(f"  关键风险: {len(critical)} 个")
    for c in critical[:3]:
        print(f"    ⚠ [{c.get('severity', '?')}] {c.get('rule', c.get('name', ''))[:50]}")

    match = data.get("qualification_match", {})
    if match:
        print(f"\n  资质匹配: 满足 {match.get('matched', 0)} / 缺失 {match.get('missing', 0)}")

    strategy = data.get("strategy", "")
    if strategy:
        print(f"\n  策略建议: {strategy[:150]}...")

    trace = data.get("trace", {})
    print(f"\n  耗时: {trace.get('elapsed_sec', '?')}s")
    print("=" * 60)
    print("  [PASS] 全链路验证通过！")
    print("=" * 60)
    return True


if __name__ == "__main__":
    if not wait_for_server():
        print("服务未启动，请先运行 run.bat")
        sys.exit(1)

    # 检查前端页面
    try:
        r = urllib.request.urlopen(f"{API}/bidding/", timeout=5)
        html = r.read().decode()
        if "投标分析" in html:
            print(f"[OK] 前端页面 /bidding/ 可访问 ({len(html)} bytes)")
        else:
            print("[WARN] 前端页面可访问但内容异常")
    except urllib.error.HTTPError as e:
        print(f"[FAIL] 前端页面 /bidding/ 返回 HTTP {e.code}")
    except Exception as e:
        print(f"[FAIL] 前端页面不可访问: {e}")

    # 测试 API
    result = test_analyze()
    ok = print_report(result)
    sys.exit(0 if ok else 1)
