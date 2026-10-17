"""前置验证：Ollama Python 调用 + PDF 读取"""
import sys, json, time, requests

OLLAMA_URL = "http://localhost:11434"
PDF_DIR = r"E:\linux\fellow-student\16-zhoujiajia\2026-10-15-知识图谱\09-装备文档\11111"

# 1. Ollama 测试
print("=" * 60)
print("📡 Ollama /api/tags")
print("=" * 60)
r = requests.get(f"{OLLAMA_URL}/api/tags", timeout=10)
models = r.json()["models"]
for m in models:
    print(f"  ✅ {m['name']}  ({m['size']/1e9:.1f} GB, ctx={m['details']['context_length']})")

print("\n" + "=" * 60)
print("🧠 Ollama 推理测试 (qwen3.5:4b) —— Python 长 timeout")
print("=" * 60)
t0 = time.time()
resp = requests.post(f"{OLLAMA_URL}/api/generate", json={
    "model": "qwen3.5:4b",
    "prompt": "你好，请只回复两个字：好的",
    "stream": False,
    "options": {"num_ctx": 512, "temperature": 0.1}
}, timeout=600)
dt = time.time() - t0
data = resp.json()
print(f"  回复: '{data.get('response', '')}'")
print(f"  耗时: {dt:.1f}s  (eval_count={data.get('eval_count','?')}, eval_duration={data.get('eval_duration','?')})")
print(f"  ✅ Ollama Python 连通正常")

# 2. PDF 测试
print("\n" + "=" * 60)
print("📄 读取 PDF 内容 (PyMuPDF)")
print("=" * 60)
import fitz, os
pdfs = sorted([f for f in os.listdir(PDF_DIR) if f.endswith(".pdf")])
print(f"  发现 {len(pdfs)} 个 PDF:")
for p in pdfs:
    print(f"    - {p}")

first = os.path.join(PDF_DIR, pdfs[0])
print(f"\n  读取第一个 PDF: {pdfs[0]}")
doc = fitz.open(first)
print(f"  页数: {doc.page_count}")
text = ""
for i in range(min(3, doc.page_count)):
    text += doc[i].get_text() + "\n"
doc.close()
print(f"  前 3 页文本前 800 字:")
print(f"  {text[:800]}...")
print(f"  ✅ PDF 可读（共 {len(text)} 字）")
