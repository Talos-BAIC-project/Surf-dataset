(function () {
  "use strict";
  const DATA = window.REGION_VIEWER_DATA;
  const NS = "http://www.w3.org/2000/svg";
  const COLORS = ["#48b5ff", "#d17bff", "#38d28b", "#ff9e4a", "#f06d9a"];
  let sample = DATA.samples[0];
  let currentCase = sample.cases[0] || null;
  const $ = (id) => document.getElementById(id);
  const canvas = $("canvas");
  const tooltip = $("tooltip");

  function el(tag, attrs, parent) {
    const n = document.createElementNS(NS, tag);
    Object.entries(attrs || {}).forEach(([k, v]) => n.setAttribute(k, String(v)));
    (parent || canvas).appendChild(n); return n;
  }
  function esc(text) { return String(text ?? ""); }
  function sy(y) { return sample.height - y; }
  function path(poly, close) {
    const d = poly.map((p, i) => `${i ? "L" : "M"}${p[0].toFixed(3)},${sy(p[1]).toFixed(3)}`).join(" ");
    return close ? d + " Z" : d;
  }
  function hover(node, text) {
    node.addEventListener("mousemove", (event) => {
      const rect = canvas.parentElement.getBoundingClientRect();
      tooltip.style.left = `${event.clientX - rect.left}px`;
      tooltip.style.top = `${event.clientY - rect.top}px`;
      tooltip.textContent = text; tooltip.classList.remove("hidden");
    });
    node.addEventListener("mouseleave", () => tooltip.classList.add("hidden"));
  }
  function faceMap() {
    const m = new Map();
    [...(sample.cells || []), ...(sample.subcells || [])].forEach((f) => m.set(f.id, f));
    return m;
  }
  function entityNames(response, kind) {
    const regions = response?.regions?.length ? response.regions : (response?.candidates || []);
    const names = [];
    for (const r of regions) for (const ref of r.entity_refs || []) {
      const name = String(ref.stable_ref || "").split("/").pop();
      const t = ref.entity_type === "face" ? "faces" : ref.entity_type === "point" ? "points" : "curves";
      if (t === kind && !names.includes(name)) names.push(name);
    }
    return names;
  }
  function goldForCase(c) {
    const label = c?.expected?.label_id;
    return (sample.gold_regions || []).filter((r) => !label || r.label_id === label);
  }
  function draw() {
    canvas.innerHTML = "";
    const margin = Math.max(sample.width, sample.height) * .08 + 3;
    canvas.setAttribute("viewBox", `${-margin} ${-margin} ${sample.width + 2 * margin} ${sample.height + 2 * margin}`);
    const gGold = el("g", { id: "gold-layer" });
    const gPred = el("g", { id: "pred-layer" });
    const gGeom = el("g", { id: "geometry-layer" });
    const gText = el("g", { id: "label-layer" });
    const fm = faceMap();
    const gold = goldForCase(currentCase);
    if ($("gold-toggle").checked) {
      gold.forEach((r) => {
        (r.faces || []).forEach((id) => { const f = fm.get(id); if (f) el("path", { d:path(f.polygon,true), class:"gold-face" }, gGold); });
        (r.curves || []).forEach((name) => { const c = sample.curves[name]; if (c) el("path", { d:path(c.poly), class:"gold-curve" }, gGold); });
      });
    }
    const response = currentCase?.response;
    const regionList = response?.regions?.length ? response.regions : (response?.candidates || []);
    const candidateMode = response && response.decision === "needs_confirmation" && !response.regions.length;
    if ($("pred-toggle").checked) {
      regionList.forEach((r, idx) => {
        const color = COLORS[idx % COLORS.length];
        (r.entity_refs || []).forEach((ref) => {
          const name = String(ref.stable_ref || "").split("/").pop();
          const type = ref.entity_type;
          if (type === "curve" && sample.curves[name]) {
            const node = el("path", { d:path(sample.curves[name].poly), class: candidateMode ? "candidate-curve" : "pred-curve", stroke: color }, gPred);
            hover(node, `${r.region_id} · ${name} · ${Number(r.confidence || 0).toFixed(3)}`);
          } else if (type === "face" && fm.has(name)) {
            const node = el("path", { d:path(fm.get(name).polygon,true), class: candidateMode ? "candidate-face" : "pred-face", stroke: color }, gPred);
            hover(node, `${r.region_id} · ${name}`);
          }
        });
      });
    }
    Object.entries(sample.curves).forEach(([name, c]) => {
      const node = el("path", { d:path(c.poly), class:"geom-curve" }, gGeom);
      hover(node, `${name} · ${c.start} → ${c.end}`);
      if ($("edge-toggle").checked) {
        const mid = c.poly[Math.floor(c.poly.length / 2)] || c.poly[0];
        const label = el("text", { x:mid[0], y:sy(mid[1]), class:"edge-label", "text-anchor":"middle" }, gText);
        label.textContent = name;
      }
    });
    if ($("point-toggle").checked) Object.entries(sample.points).forEach(([name, p]) => {
      const label = el("text", { x:p[0], y:sy(p[1]), class:"point-label" }, gText); label.textContent = name;
    });
    Object.entries(sample.points).forEach(([, p]) => el("circle", { cx:p[0], cy:sy(p[1]), r:Math.max(sample.width,sample.height)*.006+.2, class:"geom-point" }, gGeom));
    renderStatus(); renderDetails();
  }
  function renderStatus() {
    const response = currentCase?.response || { decision:"unsupported", evidence:["未选择测试 case"] };
    const label = response.label ? `${response.label.label_id} (${Number(response.label.confidence || 0).toFixed(3)})` : "无 Label";
    $("status").innerHTML = `<span class="badge ${response.decision}">${esc(response.decision)}</span> ` +
      `<span>${esc(label)} · ${esc(response.resolver || "rules")} · ${Number(response.latency_ms || 0).toFixed(2)} ms</span>`;
  }
  function chips(items, cls) { return (items || []).map((x) => `<span class="chip ${cls || ""}">${esc(x)}</span>`).join("") || `<span class="muted">无</span>`; }
  function renderDetails() {
    const c = currentCase, r = c?.response || {}, cmp = c?.comparison || {};
    $("case-panel").innerHTML = `<h3>Case / Resolver</h3>` +
      `<div class="row"><b>${esc(c?.case_id || "")}</b></div>` +
      `<div class="row">Prompt：${esc(c?.prompt || "")}</div>` +
      `<div class="row">Expected：${esc(c?.expected?.label_id || "")} · ${esc(c?.expected?.output_type || "")}</div>` +
      `<div class="row">Selector：${esc(JSON.stringify(c?.expected?.selector || r.selector || {}))}</div>` +
      `<div class="row">Evidence：${chips(r.evidence || [], "")}</div>`;
    const pk = cmp.per_kind || {};
    $("comparison-panel").innerHTML = `<h3>Gold / Rules entity 对比</h3>` +
      ["curves", "points", "faces"].map((kind) => {
        const row = pk[kind] || {}; return `<div class="row"><b>${kind}</b><br>` +
          `<span class="chip gold">gold ${row.gold?.length || 0}</span>` + `<span class="chip pred">shown ${row.predicted?.length || 0}</span>` +
          `<span class="chip miss">missing ${row.missing?.length || 0}</span>` + `<span class="chip extra">extra ${row.extra?.length || 0}</span><br>` +
          `Gold: ${chips(row.gold, "gold")}<br>Shown: ${chips(row.predicted, "pred")}</div>`;
      }).join("") + `<div class="row muted">Gold 是 silver 夹具；needs_confirmation 下橙色虚线只表示候选，不是修改授权。</div>`;
  }
  function fillCases() {
    const select = $("case-select"); select.innerHTML = "";
    (sample.cases || []).forEach((c, i) => { const o = document.createElement("option"); o.value = c.case_id; o.textContent = `${i+1}. ${c.prompt}`; select.appendChild(o); });
    if (currentCase) select.value = currentCase.case_id;
    $("prompt-input").value = currentCase?.prompt || "";
  }
  function chooseSample(sectionId) {
    sample = DATA.samples.find((s) => s.section_id === sectionId) || DATA.samples[0];
    currentCase = sample.cases[0] || null; fillCases(); draw();
    document.querySelectorAll(".sample").forEach((n) => n.classList.toggle("active", n.dataset.id === sample.section_id));
  }
  function renderSidebar() {
    $("dataset-note").textContent = DATA.note;
    $("dataset-stats").textContent = `${DATA.sample_count} 个截面样本 · ${DATA.case_count} 个测试 case`;
    const list = $("sample-list"); list.innerHTML = "";
    DATA.samples.forEach((s) => { const n = document.createElement("div"); n.className = "sample"; n.dataset.id = s.section_id; n.innerHTML = `<span>${esc(s.section_id)}</span><small>${esc(s.family)} · ${s.width}×${s.height}</small>`; n.onclick = () => chooseSample(s.section_id); list.appendChild(n); });
  }
  $("case-select").onchange = (e) => { currentCase = sample.cases.find((c) => c.case_id === e.target.value) || sample.cases[0]; $("prompt-input").value = currentCase?.prompt || ""; draw(); };
  $("run-button").onclick = () => { const q = $("prompt-input").value.trim(); const found = sample.cases.find((c) => c.prompt === q || c.case_id === q); if (found) { currentCase = found; fillCases(); draw(); } else { alert("当前静态 viewer 只包含已导出的测试 prompts；请先把新 case 加入 cases.yaml 后重新导出。"); } };
  ["gold-toggle", "pred-toggle", "edge-toggle", "point-toggle"].forEach((id) => $(id).onchange = draw);
  renderSidebar(); chooseSample(sample.section_id);
  const params = new URLSearchParams(location.search); if (params.get("section")) chooseSample(params.get("section"));
  if (params.get("case")) { const found = sample.cases.find((c) => c.case_id === params.get("case")); if (found) { currentCase = found; fillCases(); draw(); } }
})();
