import os
import requests
from bs4 import BeautifulSoup

# ================= 配置区（四个都填） =================
KB_URL = "http://61.182.88.214:8090/jsxsd/xskb/xskb_list.do"   # 课表请求地址
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/157.0.0.0 Safari/537.36"                        # 抓包里的 User-Agent
REFERER = "http://61.182.88.214:8090/jsxsd/framework/xsMain.jsp"   # 抓包里的 Referer，可能和 KB_URL 不同
# GitHub Actions 从 Secret 读取 KB_COOKIE；本地测试可临时把 Cookie 粘在第二个参数里
COOKIE = os.environ.get("KB_COOKIE", "")
# =====================================================


def fetch_html():
    if not COOKIE:
        raise RuntimeError("没有可用 Cookie：本地请填 COOKIE，Actions 请设置 KB_COOKIE")
    headers = {
        "Cookie": COOKIE,
        "User-Agent": USER_AGENT,
        "Referer": REFERER,
    }

    r = requests.get(KB_URL, headers=headers, timeout=20)
    r.encoding = r.apparent_encoding

    if "kbcontent" not in r.text:
        raise RuntimeError("返回内容里没有 kbcontent，Cookie 可能过期，或 Referer/URL 不对")

    return r.text


def parse_html(html):
    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table", id="kbtable")
    if not table:
        raise RuntimeError("没找到 id=kbtable 的表格")

    # 只取这个表格自己的 tr，排除嵌套表格
    trs = [tr for tr in table.find_all("tr") if tr.find_parent("table") is table]

    # 找表头行：包含“星期一”的那一行
    header_tr = None
    days = []
    for tr in trs:
        texts = [th.get_text(strip=True) for th in tr.find_all("th")]
        if "星期一" in texts:
            header_tr = tr
            days = [t for t in texts if t]
            break

    if not days:
        raise RuntimeError("没找到星期表头")

    grid = {}
    section_order = []

    for tr in trs:
        if tr is header_tr:
            continue

        th = tr.find("th")
        if not th:
            continue

        th_lines = [x.strip() for x in th.get_text("\n", strip=True).split("\n") if x.strip()]
        section_name = th_lines[0] if th_lines else ""
        section_time = th_lines[1] if len(th_lines) > 1 else ""

        if section_name not in [s[0] for s in section_order]:
            section_order.append((section_name, section_time))

        tds = tr.find_all("td")
        for day_idx, td in enumerate(tds):
            day = days[day_idx] if day_idx < len(days) else f"第{day_idx + 1}天"

            for div in td.find_all("div"):
                cls = div.get("class") or []
                if isinstance(cls, str):
                    cls = [cls]
                if not any("kbcontent" in c for c in cls):
                    continue

                # 一个格子可能有多门课，用分隔线拆开
                for part in div.decode_contents().split("---------------------"):
                    part = part.strip()
                    if not part:
                        continue

                    seg = BeautifulSoup(part, "html.parser")

                    teacher_tag = seg.find("font", title="老师") or seg.find("font", title="教师")
                    weeks_tag = seg.find("font", title="周次(节次)") or seg.find("font", title="周次")
                    room_tag = seg.find("font", title="教室") or seg.find("font", title="上课地点")

                    teacher = teacher_tag.get_text(strip=True) if teacher_tag else ""
                    weeks = weeks_tag.get_text(strip=True) if weeks_tag else ""
                    room = room_tag.get_text(strip=True) if room_tag else ""

                    # 删掉 font/span，剩下的第一行就是课程名
                    for tag in seg.find_all(["font", "span"]):
                        tag.decompose()

                    lines = [x.strip() for x in seg.get_text("\n", strip=True).split("\n") if x.strip()]
                    course = lines[0] if lines else ""
                    course = course.replace("\xa0", " ").strip()

                    if course:
                        item = (course, teacher, weeks, room)
                        grid.setdefault((day, section_name), [])
                        if item not in grid[(day, section_name)]:
                            grid[(day, section_name)].append(item)

    return grid, days, section_order


def render_html(grid, days, section_order):
    rows = ""

    for section_name, section_time in section_order:
        cells = f'<td class="sec"><b>{section_name}</b><br><span>{section_time}</span></td>'

        for day in days:
            items = grid.get((day, section_name), [])

            if items:
                inner = ""
                for course, teacher, weeks, room in items:
                    inner += '<div class="course">'
                    inner += f'<div class="name">{course}</div>'
                    if teacher:
                        inner += f'<div class="meta">👤 {teacher}</div>'
                    if room:
                        inner += f'<div class="meta">📍 {room}</div>'
                    if weeks:
                        inner += f'<div class="meta">🗓 {weeks}</div>'
                    inner += '</div>'
                cells += f'<td class="has-course">{inner}</td>'
            else:
                cells += '<td></td>'

        rows += f"<tr>{cells}</tr>"

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>实时课表</title>
<style>
  body {{ margin:0; padding:8px; font-family:-apple-system,"PingFang SC","Microsoft YaHei",sans-serif; background:#f5f6f8; }}
  h1 {{ font-size:18px; text-align:center; margin:8px 0; }}
  .wrap {{ overflow-x:auto; -webkit-overflow-scrolling:touch; }}
  table {{ border-collapse:collapse; width:100%; min-width:760px; background:#fff; }}
  th {{ background:#4a6fa5; color:#fff; font-size:13px; padding:8px 4px; position:sticky; top:0; }}
  td {{ border:1px solid #e3e6ea; vertical-align:top; padding:4px; font-size:11px; min-width:100px; }}
  td.sec {{ background:#eef2f7; text-align:center; font-size:11px; width:70px; white-space:nowrap; }}
  td.sec span {{ color:#888; font-size:10px; }}
  .course {{ background:#fafbfc; border-left:4px solid #4a6fa5; border-radius:4px; padding:4px 5px; margin-bottom:4px; }}
  .name {{ font-weight:600; font-size:12px; margin-bottom:2px; line-height:1.3; }}
  .meta {{ color:#666; font-size:10px; line-height:1.4; }}
</style>
</head>
<body>
<h1>实时课表</h1>
<div class="wrap">
<table>
<tr><th>节次</th>{"".join(f"<th>{d}</th>" for d in days)}</tr>
{rows}
</table>
</div>
</body>
</html>"""


def main():
    html = fetch_html()
    grid, days, section_order = parse_html(html)
    out = render_html(grid, days, section_order)

    with open("index.html", "w", encoding="utf-8") as f:
        f.write(out)

    total = sum(len(v) for v in grid.values())
    print(f"已生成 index.html，共 {total} 个课程条目")


if __name__ == "__main__":
    main()