"""
Crash-1500.txt (CCD 주석 파일) 파서.

한 줄 형식:
    vidname, [50개 binlabels], youtube_id, timing, day/night, weather, ego

- binlabels: 50프레임 각각 사고(1)/정상(0)  → 학습 정답
- 리스트 안에 쉼표가 있어서 split(',')로는 못 나눔. 대괄호 기준으로 자른다.
"""
import ast
from pathlib import Path


def parse_line(line):
    """한 줄 → dict. 형식이 안 맞으면 None."""
    line = line.strip()
    if not line or "[" not in line:
        return None

    vid, rest = line.split(",[", 1)
    label_str, tail = rest.split("],", 1)
    binlabels = ast.literal_eval("[" + label_str + "]")
    parts = tail.split(",")

    # tail = youtube_id, timing, day/night, weather, ego (5개)
    ytb_id = parts[0] if len(parts) > 0 else ""
    day_night = parts[2] if len(parts) > 2 else ""
    weather = parts[3] if len(parts) > 3 else ""
    ego = parts[4] if len(parts) > 4 else ""

    accident_frame = binlabels.index(1) if 1 in binlabels else None

    return {
        "vid": vid.strip(),
        "binlabels": binlabels,
        "nframes": len(binlabels),
        "accident_frame": accident_frame,   # 최초 사고 프레임 (없으면 None)
        "ytb_id": ytb_id.strip(),
        "day_night": day_night.strip(),
        "weather": weather.strip(),
        "ego": ego.strip(),
    }


def load_labels(txt_path):
    """Crash-1500.txt 전체 → {vid: dict}."""
    txt_path = Path(txt_path)
    out = {}
    for line in txt_path.read_text(encoding="utf-8").splitlines():
        row = parse_line(line)
        if row:
            out[row["vid"]] = row
    return out


if __name__ == "__main__":
    import sys
    labels = load_labels(sys.argv[1])
    print(f"총 {len(labels)}개 영상")
    for vid in list(labels)[:3]:
        r = labels[vid]
        f = r["accident_frame"]
        print(f"  {vid}: {r['nframes']}프레임, 사고={f} "
              f"({f/10:.1f}s)" if f is not None else f"  {vid}: 사고없음")
