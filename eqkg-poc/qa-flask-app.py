"""
装备知识问答 Flask Web UI v2 —— 问答 + 文档导入
启动: py -3.12 -u eqkg-poc/qa-flask-app.py
访问: http://localhost:5000
"""
import os, sys, json, time, uuid
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from flask import Flask, render_template_string, request, jsonify, send_from_directory
from werkzeug.utils import secure_filename

from qa_engine import ask, run_cypher, driver, NEO4J_URI, NEO4J_USER, NEO4J_PWD
from eqkg_extractor import (
    read_pdf_from_bytes, detect_equipment_name, extract_from_text, merge_triples
)

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024  # 50MB 上限
ALLOWED_EXT = {"pdf"}

# 抽取结果暂存（内存 dict，生产环境应该用 Redis）
PENDING_EXTRACTS = {}  # extract_id -> {equipment, triples, text_len, is_scanned, filename}


def _allowed(name: str) -> bool:
    return "." in name and name.rsplit(".", 1)[1].lower() in ALLOWED_EXT


# ================================================================
# 前端 HTML
# ================================================================
HTML = r"""
<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<title>装备知识图谱问答 & 导入</title>
<style>
  body { font-family: -apple-system, "PingFang SC", "Microsoft YaHei", sans-serif; max-width: 1040px; margin: 40px auto; padding: 0 20px; background:#f5f6fa; color:#222; }
  h1 { color:#2c3e50; border-bottom:3px solid #3498db; padding-bottom:12px; }
  h2 { color:#2c3e50; margin-top:0; font-size:18px; }
  .box { background:#fff; border-radius:10px; padding:20px 24px; margin:16px 0; box-shadow:0 2px 8px rgba(0,0,0,0.06); }
  .box h3 { margin-top:0; }
  .tab-bar { display:flex; gap:0; border-bottom:2px solid #dcdfe6; margin-bottom:18px; }
  .tab-btn { padding:10px 22px; background:#ecf0f1; border:none; font-size:15px; cursor:pointer; border-top-left-radius:8px; border-top-right-radius:8px; margin-right:2px; }
  .tab-btn.active { background:#3498db; color:white; }
  .tab-content { display:none; }
  .tab-content.active { display:block; }

  input[type=text] { width:100%; padding:12px 14px; border:1px solid #dcdfe6; border-radius:8px; font-size:15px; box-sizing:border-box; }
  input[type=text]:focus { outline:none; border-color:#3498db; }
  .btn { background:#3498db; color:white; border:none; padding:10px 24px; border-radius:8px; font-size:15px; cursor:pointer; margin:6px 4px 0 0; }
  .btn:hover { background:#2980b9; }
  .btn.secondary { background:#95a5a6; }
  .btn.secondary:hover { background:#7f8c8d; }
  .btn.success { background:#27ae60; }
  .btn.success:hover { background:#229954; }
  .btn:disabled { background:#bdc3c7; cursor:not-allowed; }
  .example { display:inline-block; background:#ecf0f1; padding:6px 12px; border-radius:20px; margin:4px; cursor:pointer; font-size:13px; }
  .example:hover { background:#d5dbdb; }
  pre { background:#2c3e50; color:#ecf0f1; padding:14px; border-radius:8px; overflow:auto; font-size:13px; line-height:1.5; }
  .mode { font-size:12px; color:#7f8c8d; }
  .mode.rule { color:#27ae60; font-weight:bold; }
  .mode.none { color:#e74c3c; }
  label { font-size:13px; color:#555; }

  /* 上传区 */
  .upload-zone { border:2px dashed #3498db; border-radius:12px; padding:40px; text-align:center; cursor:pointer; transition:all 0.2s; background:#fafcff; }
  .upload-zone:hover { background:#eaf4fb; border-color:#2980b9; }
  .upload-zone.dragover { background:#d4ebf8; border-color:#1a5276; }
  .upload-zone input[type=file] { display:none; }
  .upload-zone .hint { color:#7f8c8d; font-size:14px; margin-top:8px; }
  .upload-zone .big-icon { font-size:40px; }

  /* 扫描件警告 */
  .warn { background:#fdecea; border-left:4px solid #e74c3c; padding:12px 16px; border-radius:6px; color:#c0392b; margin:10px 0; font-size:14px; }
  .info { background:#eaf7ed; border-left:4px solid #27ae60; padding:12px 16px; border-radius:6px; color:#1e8449; margin:10px 0; font-size:14px; }

  /* 预览表格 */
  table { width:100%; border-collapse:collapse; margin-top:14px; font-size:13px; }
  th, td { border:1px solid #ecf0f1; padding:8px 10px; text-align:left; }
  th { background:#f8f9fa; font-weight:600; color:#2c3e50; }
  tr:hover { background:#f8f9fa; }
  .badge { display:inline-block; padding:2px 8px; border-radius:10px; font-size:11px; font-weight:bold; }
  .badge.Equipment { background:#3498db; color:white; }
  .badge.Component { background:#2ecc71; color:white; }
  .badge.Fault { background:#e74c3c; color:white; }
  .badge.Function { background:#9b59b6; color:white; }
  .badge.Attribute { background:#f39c12; color:white; }
  .badge.Solution { background:#1abc9c; color:white; }

  .preview-header { display:flex; justify-content:space-between; align-items:center; margin-top:16px; }
  .equip-name { font-size:16px; font-weight:bold; color:#2c3e50; }
  .stats { display:flex; gap:16px; font-size:13px; color:#7f8c8d; }
  .stats .num { font-size:20px; font-weight:bold; color:#2c3e50; }
</style>
</head>
<body>

<h1>🔬 装备知识图谱 问答 & 文档导入</h1>

<div class="tab-bar">
  <button class="tab-btn active" onclick="switchTab('ask')">❓ 问答</button>
  <button class="tab-btn" onclick="switchTab('import')">📥 文档导入</button>
  <button class="tab-btn" onclick="showGraph()">📊 图谱预览</button>
  <button class="tab-btn" onclick="showOverview()">📈 图谱统计</button>
</div>

<!-- ============ 问答 Tab ============ -->
<div id="tab-ask" class="tab-content active">
  <div class="box">
    <h3>❓ 提问</h3>
    <input type="text" id="q" placeholder="例如：测序仪有哪些部件？" />
    <div style="margin-top:10px;">
      <input type="checkbox" id="use_llm" />
      <label for="use_llm">启用 LLM Text2Cypher 兜底（CPU 较慢）</label>
    </div>
    <button class="btn" onclick="askQ()">提交问答</button>
  </div>

  <div class="box">
    <h4>💡 试试这些问题：</h4>
    <span class="example" onclick="fillQ('有哪些装备')">有哪些装备</span>
    <span class="example" onclick="fillQ('测序仪有哪些部件')">测序仪有哪些部件</span>
    <span class="example" onclick="fillQ('测序仪有什么功能')">测序仪有什么功能</span>
    <span class="example" onclick="fillQ('测序仪有哪些常见故障')">测序仪有哪些常见故障</span>
    <span class="example" onclick="fillQ('装备参数有哪些')">装备参数有哪些</span>
  </div>

  <div class="box" id="answer_box" style="display:none;">
    <h3>📋 答案</h3>
    <div id="answer" style="white-space:pre-wrap; line-height:1.7;"></div>
    <pre id="cypher" style="display:none;"></pre>
    <div id="meta" class="mode"></div>
  </div>
</div>

<!-- ============ 文档导入 Tab ============ -->
<div id="tab-import" class="tab-content">
  <div class="box">
    <h3>📥 上传装备 PDF</h3>
    <div class="upload-zone" id="uploadZone" onclick="document.getElementById('fileInput').click()">
      <div class="big-icon">📄</div>
      <div><b>点击选择 PDF</b> 或把文件拖到这里</div>
      <div class="hint">支持 .pdf 格式 · 单个文件 ≤ 50MB · 装备说明书/彩页/手册</div>
      <input type="file" id="fileInput" accept=".pdf" />
    </div>
    <div id="uploadStatus" style="margin-top:12px;"></div>
  </div>

  <div class="box" id="previewBox" style="display:none;">
    <h3>🔍 抽取结果预览</h3>
    <div id="scanWarn" class="warn" style="display:none;">⚠ 这是扫描件 PDF，无法提取文字层。建议先用 OCR 工具转文字后再上传。</div>
    <div id="textLenWarn" class="warn" style="display:none;"></div>

    <div class="preview-header">
      <div>
        <span class="equip-name" id="equipName">-</span>
        <div class="stats" id="stats">-</div>
      </div>
      <div>
        <select id="filterLabel" onchange="renderTable()" style="padding:6px 10px; border-radius:6px; border:1px solid #dcdfe6;">
          <option value="">全部标签</option>
          <option value="Equipment">Equipment</option>
          <option value="Component">Component</option>
          <option value="Fault">Fault</option>
          <option value="Function">Function</option>
          <option value="Attribute">Attribute</option>
          <option value="Solution">Solution</option>
        </select>
      </div>
    </div>

    <table id="tripleTable">
      <thead><tr><th style="width:25%;">头实体</th><th style="width:12%;">关系</th><th style="width:25%;">尾实体</th><th style="width:12%;">标签</th></tr></thead>
      <tbody></tbody>
    </table>
    <div style="margin-top:10px; font-size:13px; color:#7f8c8d;" id="tableHint"></div>

    <div style="margin-top:18px;">
      <button class="btn success" id="commitBtn" onclick="commitToNeo4j()">✅ 确认导入到知识图谱</button>
      <button class="btn secondary" onclick="clearPreview()">取消</button>
    </div>
  </div>

  <div class="box" id="commitBox" style="display:none;">
    <h3>✅ 导入完成</h3>
    <div id="commitResult"></div>
    <button class="btn secondary" onclick="switchTab('ask')">去问答试试</button>
    <button class="btn secondary" onclick="showGraph()">看图谱</button>
  </div>
</div>

<!-- ============ 图谱预览 ============ -->
<div id="graph_box" class="box" style="display:none;">
  <h3>📊 Neo4j Browser（嵌入预览）</h3>
  <iframe style="width:100%; height:520px; border:1px solid #dcdfe6; border-radius:8px;" src="http://localhost:7474/browser/"></iframe>
  <div style="font-size:13px; color:#7f8c8d; margin-top:6px;">如果没显示，请直接打开 <a href="http://localhost:7474/browser/" target="_blank">http://localhost:7474/browser/</a></div>
</div>

<script>
let pendingExtract = null; // {equipment, triples, extract_id, ...}

// ============ Tab 切换 ============
function switchTab(name) {
  document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
  document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
  const idx = {ask:0, import:1}[name] ?? 0;
  document.querySelectorAll('.tab-btn')[idx].classList.add('active');
  document.querySelectorAll('.tab-content')[idx].classList.add('active');
  document.getElementById('graph_box').style.display = 'none';
}

// ============ 问答 ============
function fillQ(t) { document.getElementById('q').value = t; }
document.addEventListener('keydown', e => { if (e.key === 'Enter' && document.getElementById('q') === document.activeElement) askQ(); });

async function askQ() {
  const q = document.getElementById('q').value.trim();
  if (!q) return;
  const useLLM = document.getElementById('use_llm').checked;
  const btn = event?.target;
  if (btn) { btn.disabled = true; btn.textContent = '思考中...'; }
  try {
    const r = await fetch('/api/ask', {
      method: 'POST', headers: {'Content-Type':'application/json'},
      body: JSON.stringify({question: q, use_llm: useLLM})
    });
    const data = await r.json();
    const box = document.getElementById('answer_box');
    box.style.display = 'block';
    document.getElementById('answer').textContent = data.answer || '(无答案)';
    const cy = document.getElementById('cypher');
    if (data.cypher) { cy.style.display='block'; cy.textContent = 'Cypher: ' + data.cypher; } else cy.style.display='none';
    const meta = document.getElementById('meta');
    const label = data.mode === 'rule' ? '⚡ 规则模板' : data.mode === 'llm' ? '🤖 LLM Text2Cypher' : '⚠ 未命中';
    meta.textContent = `${label}  |  ${(data.elapsed || 0).toFixed(1)}s`;
    meta.className = 'mode ' + (data.mode || 'none');
  } catch(e) { alert('出错了: ' + e); }
  if (btn) { btn.disabled = false; btn.textContent = '提交问答'; }
}

function showGraph() {
  document.getElementById('graph_box').style.display = 'block';
  document.getElementById('graph_box').scrollIntoView({behavior:'smooth'});
}
async function showOverview() {
  const r = await fetch('/api/overview');
  alert(JSON.stringify(await r.json(), null, 2));
}

// ============ 文档导入 ============
const zone = document.getElementById('uploadZone');
const fileInput = document.getElementById('fileInput');

zone.addEventListener('dragover', e => { e.preventDefault(); zone.classList.add('dragover'); });
zone.addEventListener('dragleave', () => zone.classList.remove('dragover'));
zone.addEventListener('drop', e => {
  e.preventDefault();
  zone.classList.remove('dragover');
  if (e.dataTransfer.files.length) handleFile(e.dataTransfer.files[0]);
});
fileInput.addEventListener('change', e => { if (e.target.files.length) handleFile(e.target.files[0]); });

async function handleFile(file) {
  if (!file.name.toLowerCase().endsWith('.pdf')) { alert('只接受 .pdf 文件'); return; }
  if (file.size > 50*1024*1024) { alert('文件超过 50MB'); return; }

  const status = document.getElementById('uploadStatus');
  status.innerHTML = '<div class="info">⏳ 上传并抽取中...</div>';

  const fd = new FormData();
  fd.append('file', file);
  const t0 = Date.now();
  try {
    const r = await fetch('/api/upload', {method:'POST', body:fd});
    const data = await r.json();
    if (!r.ok) { status.innerHTML = `<div class="warn">❌ 上传失败: ${data.error || r.status}</div>`; return; }
    const elapsed = ((Date.now()-t0)/1000).toFixed(1);
    status.innerHTML = `<div class="info">✅ 抽取完成 (${elapsed}s)</div>`;
    pendingExtract = data;
    renderPreview(data);
  } catch(e) {
    status.innerHTML = `<div class="warn">❌ 网络错误: ${e}</div>`;
  }
}

function renderPreview(data) {
  document.getElementById('previewBox').style.display = 'block';
  document.getElementById('commitBox').style.display = 'none';
  document.getElementById('equipName').textContent = `🏷 ${data.equipment}`;

  // 扫描件警告
  document.getElementById('scanWarn').style.display = data.is_scanned ? 'block' : 'none';

  // 统计
  const byRel = {}; const byLabel = {};
  data.triples.forEach(t => {
    byRel[t.rel] = (byRel[t.rel]||0)+1;
    byLabel[t.tl] = (byLabel[t.tl]||0)+1;
    byLabel[t.hl] = (byLabel[t.hl]||0)+1;
  });
  document.getElementById('stats').innerHTML =
    `<span><span class="num">${data.triples.length}</span> 条三元组</span>` +
    `<span>${Object.entries(byRel).map(([k,v])=>k+':'+v).join(' · ')}</span>` +
    `<span>📄 ${data.text_len} 字</span>`;

  renderTable();
}

function renderTable() {
  if (!pendingExtract) return;
  const filter = document.getElementById('filterLabel').value;
  const tbody = document.querySelector('#tripleTable tbody');
  let rows = pendingExtract.triples;
  if (filter) rows = rows.filter(t => t.tl === filter || t.hl === filter);
  const show = rows.slice(0, 200);
  tbody.innerHTML = show.map(t => `
    <tr>
      <td>${t.head}</td>
      <td><span class="badge ${t.hl}">${t.hl}</span> ${t.rel}</td>
      <td>${t.tail}</td>
      <td><span class="badge ${t.tl}">${t.tl}</span></td>
    </tr>`).join('');
  document.getElementById('tableHint').textContent =
    `显示 ${show.length}/${rows.length} 条${rows.length>200?' (前200)':''}`;
}

async function commitToNeo4j() {
  const btn = document.getElementById('commitBtn');
  btn.disabled = true; btn.textContent = '导入中...';
  try {
    const r = await fetch('/api/commit', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({extract_id: pendingExtract.extract_id})
    });
    const data = await r.json();
    const box = document.getElementById('commitBox');
    box.style.display = 'block';
    const el = document.getElementById('commitResult');
    if (data.error) { el.innerHTML = `<div class="warn">❌ 导入失败: ${data.error}</div>`; }
    else {
      el.innerHTML = `
        <div class="info">✅ 成功导入 <b>${data.total}</b> 条三元组</div>
        <div style="font-size:13px; color:#7f8c8d; margin-top:6px;">
          新增节点 ${data.added_nodes} · 新增关系 ${data.added_rels}
        </div>`;
    }
  } catch(e) { alert('导入出错: '+e); }
  btn.disabled = false; btn.textContent = '✅ 确认导入到知识图谱';
}

function clearPreview() {
  document.getElementById('previewBox').style.display = 'none';
  document.getElementById('commitBox').style.display = 'none';
  document.getElementById('uploadStatus').innerHTML = '';
  pendingExtract = null;
  fileInput.value = '';
}
</script>
</body>
</html>
"""


# ================================================================
# Flask 路由
# ================================================================
@app.route("/")
def index():
    return render_template_string(HTML)


@app.route("/api/ask", methods=["POST"])
def api_ask():
    data = request.get_json()
    q = data.get("question", "").strip()
    if not q:
        return jsonify({"error": "问题不能为空"}), 400
    result = ask(q, use_llm=data.get("use_llm", False))
    return jsonify(result)


@app.route("/api/overview")
def api_overview():
    """图谱统计"""
    out = {}
    try:
        out["node_labels"] = run_cypher("MATCH (n) RETURN labels(n)[0] AS label, count(n) AS cnt ORDER BY cnt DESC")
        out["rel_types"] = run_cypher("MATCH ()-[r]->() RETURN type(r) AS rel, count(r) AS cnt ORDER BY cnt DESC")
        out["nodes"] = run_cypher("MATCH (n) RETURN count(n) AS c")[0]["c"]
        out["rels"] = run_cypher("MATCH ()-[r]->() RETURN count(r) AS c")[0]["c"]
    except Exception as e:
        out["error"] = str(e)
    return jsonify(out)


@app.route("/api/upload", methods=["POST"])
def api_upload():
    """接收 PDF → 返回抽取预览"""
    if "file" not in request.files:
        return jsonify({"error": "没有上传文件"}), 400
    f = request.files["file"]
    if not f.filename or not _allowed(f.filename):
        return jsonify({"error": "只接受 .pdf 文件"}), 400

    data = f.read()
    if len(data) > 50 * 1024 * 1024:
        return jsonify({"error": "文件超过 50MB"}), 400

    t0 = time.time()
    try:
        text = read_pdf_from_bytes(data, f.filename)
    except Exception as e:
        return jsonify({"error": f"PDF 解析失败: {e}"}), 400

    equipment = detect_equipment_name(text, f.filename)
    triples = extract_from_text(text, equipment)
    elapsed = time.time() - t0

    is_scanned = len(text) < 50

    # 存到内存
    extract_id = uuid.uuid4().hex
    PENDING_EXTRACTS[extract_id] = {
        "equipment": equipment,
        "triples": triples,
        "text_len": len(text),
        "is_scanned": is_scanned,
        "filename": f.filename,
        "created_at": time.time(),
    }

    return jsonify({
        "extract_id": extract_id,
        "equipment": equipment,
        "triples": triples,
        "text_len": len(text),
        "is_scanned": is_scanned,
        "elapsed": round(elapsed, 2),
        "filename": f.filename,
    })


@app.route("/api/commit", methods=["POST"])
def api_commit():
    """把暂存的三元组 MERGE 进 Neo4j"""
    payload = request.get_json() or {}
    extract_id = payload.get("extract_id")
    if not extract_id or extract_id not in PENDING_EXTRACTS:
        return jsonify({"error": "找不到暂存的抽取结果，请重新上传"}), 404

    pending = PENDING_EXTRACTS.pop(extract_id)
    triples = pending["triples"]
    if not triples:
        return jsonify({"error": "没有可导入的三元组"}), 400

    try:
        # 确保 driver 活着
        try:
            driver.verify_connectivity()
        except Exception:
            driver.close()
            driver.__init__(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PWD))
        result = merge_triples(driver, triples)
    except Exception as e:
        import traceback; traceback.print_exc()
        return jsonify({"error": f"Neo4j 写入失败: {e}"}), 500

    return jsonify(result)


if __name__ == "__main__":
    print("🚀 装备知识图谱 Flask UI (问答 + 导入): http://localhost:5000")
    app.run(host="0.0.0.0", port=5000, debug=False)
