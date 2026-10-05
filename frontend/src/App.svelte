<script>
  let session = null;
  let logs = [];
  let loginUser = "surveyor";
  let loginPass = "surv123456";
  let chainage = "";
  let deltaMm = "";
  let error = "";
  let loading = false;
  let detail = null;
  let detailId = null;
  let detailError = "";
  let timer;

  $: isWriter = session?.role === "writer";

  function headers() {
    return session ? { Authorization: "Bearer " + session.token } : {};
  }

  // 真实读数：0.0 必须显示为 0，只有尚未入库的 null 才显示占位。
  function formatMm(v) {
    return v === null || v === undefined ? "—" : String(v);
  }

  async function loadDetail(id) {
    detailId = id;
    detailError = "";
    try {
      const res = await fetch(`/api/logs/${id}`, { headers: headers() });
      if (res.status === 401) {
        logout();
        return;
      }
      const data = await res.json();
      if (!res.ok) {
        detailError = data.detail || "读取详情失败";
        detail = null;
        return;
      }
      detail = data;
    } catch {
      detailError = "详情网络异常";
    }
  }

  function closeDetail() {
    detail = null;
    detailId = null;
    detailError = "";
  }

  async function refresh() {
    if (!session) return;
    const res = await fetch("/api/logs", { headers: headers() });
    if (res.status === 401) {
      logout();
      return;
    }
    if (res.ok) logs = await res.json();
    // 翻页/轮询刷新后，已打开的详情也重读，确认读数不凭空变空或变零。
    if (detailId !== null) await loadDetail(detailId);
  }

  async function login() {
    error = "";
    loading = true;
    try {
      const res = await fetch("/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username: loginUser, password: loginPass }),
      });
      const data = await res.json();
      if (!res.ok) {
        error = data.detail || "登录失败";
        return;
      }
      session = { token: data.access_token, username: data.username, role: data.role };
      localStorage.setItem("tunnel_session", JSON.stringify(session));
      await refresh();
      timer = setInterval(refresh, 2000);
    } catch {
      error = "无法连接接口";
    } finally {
      loading = false;
    }
  }

  function logout() {
    if (timer) clearInterval(timer);
    session = null;
    logs = [];
    detail = null;
    detailId = null;
    localStorage.removeItem("tunnel_session");
  }

  async function submit() {
    error = "";
    loading = true;
    try {
      const res = await fetch("/api/logs", {
        method: "POST",
        headers: { "Content-Type": "application/json", ...headers() },
        body: JSON.stringify({ chainage, delta_mm: Number(deltaMm) }),
      });
      const data = await res.json();
      if (!res.ok) {
        error = data.detail || "提交失败";
        return;
      }
      chainage = "";
      deltaMm = "";
      await refresh();
    } catch {
      error = "提交时网络异常";
    } finally {
      loading = false;
    }
  }

  const raw = localStorage.getItem("tunnel_session");
  if (raw) {
    try {
      session = JSON.parse(raw);
      refresh();
      timer = setInterval(refresh, 2000);
    } catch {
      localStorage.removeItem("tunnel_session");
    }
  }
</script>

<style>
  :global(body) {
    margin: 0;
    font-family: "Segoe UI", system-ui, sans-serif;
    background: #1c1917;
    color: #f5f5f4;
  }
  main { max-width: 960px; margin: 0 auto; padding: 1.5rem; }
  h1 { color: #fbbf24; margin: 0 0 0.25rem; }
  .sub { color: #a8a29e; margin-bottom: 1.25rem; }
  section {
    background: #292524; border: 1px solid #44403c; border-radius: 8px;
    padding: 1rem 1.25rem; margin-bottom: 1rem;
  }
  label { display: block; font-size: 0.85rem; color: #d6d3d1; margin-bottom: 0.25rem; }
  input {
    width: 100%; box-sizing: border-box; padding: 0.5rem 0.65rem; border-radius: 6px;
    border: 1px solid #57534e; background: #0c0a09; color: #fafaf9; margin-bottom: 0.75rem;
  }
  button {
    cursor: pointer; padding: 0.5rem 1rem; border: none; border-radius: 6px;
    background: #d97706; color: #fff; font-weight: 600;
  }
  button.secondary { background: #57534e; }
  .err { color: #fb7185; }
  table { width: 100%; border-collapse: collapse; font-size: 0.9rem; }
  th, td { text-align: left; padding: 0.45rem; border-bottom: 1px solid #44403c; }
  .tag { padding: 0.1rem 0.4rem; border-radius: 4px; font-size: 0.8rem; }
  .ok { background: #14532d; color: #86efac; }
  .bad { background: #7f1d1d; color: #fca5a5; }
  .pending { background: #713f12; color: #fde68a; }
  button.link { padding: 0.2rem 0.6rem; font-size: 0.8rem; }
  .detail-title { font-size: 1rem; margin: 0 0 0.75rem; color: #fbbf24; }
  .detail-grid { width: auto; margin-bottom: 0.75rem; }
  .detail-grid th { width: 6rem; color: #a8a29e; font-weight: normal; }
</style>

<main>
  <h1>隧道收敛测缝台</h1>
  {#if !session}
    <p class="sub">测量员提交桩号与收敛毫米值，接口进程内线程认领后出结论。登录框已预填可写账号 surveyor / surv123456。</p>
    <section>
      <label>用户名</label>
      <input bind:value={loginUser} autocomplete="off" />
      <label>密码</label>
      <input type="password" bind:value={loginPass} autocomplete="off" />
      <button disabled={loading} on:click={login}>登录</button>
      {#if error}<p class="err">{error}</p>{/if}
    </section>
  {:else}
    <p class="sub">已登录：{session.username}（{isWriter ? "可提交" : "只读"}）</p>
    <section>
      <button class="secondary" on:click={logout}>退出</button>
      <button class="secondary" disabled={loading} on:click={refresh}>刷新列表</button>
    </section>
    {#if isWriter}
      <section>
        <label>里程桩号</label>
        <input placeholder="例如 K20+050" bind:value={chainage} />
        <label>收敛（毫米，可正可负）</label>
        <input type="number" step="0.1" bind:value={deltaMm} />
        <button disabled={loading} on:click={submit}>提交（进入待认领）</button>
        {#if error}<p class="err">{error}</p>{/if}
      </section>
    {/if}
    <section>
      <table>
        <thead>
          <tr><th>编号</th><th>桩号</th><th>收敛mm</th><th>状态</th><th>结论</th><th>说明</th><th></th></tr>
        </thead>
        <tbody>
          {#each logs as row}
            <tr>
              <td>{row.id}</td>
              <td>{row.chainage}</td>
              <td>{formatMm(row.delta_mm)}</td>
              <td><span class="tag {row.status === 'pending' ? 'pending' : 'ok'}">{row.status === 'pending' ? '待处理' : '已完成'}</span></td>
              <td>
                {#if row.verdict}
                  <span class="tag {row.verdict === '合格' ? 'ok' : 'bad'}">{row.verdict}</span>
                {:else}—{/if}
              </td>
              <td>{row.reason ?? "—"}</td>
              <td><button class="secondary link" on:click={() => loadDetail(row.id)}>详情</button></td>
            </tr>
          {/each}
        </tbody>
      </table>
    </section>
    {#if detailId !== null}
      <section>
        <h2 class="detail-title">读数详情 #{detailId}</h2>
        {#if detailError}
          <p class="err">{detailError}</p>
        {:else if detail}
          <table class="detail-grid">
            <tbody>
              <tr><th>桩号</th><td>{detail.chainage}</td></tr>
              <tr><th>收敛mm</th><td>{formatMm(detail.delta_mm)}</td></tr>
              <tr><th>状态</th><td>{detail.status === 'pending' ? '待处理' : '已完成'}</td></tr>
              <tr><th>结论</th><td>{detail.verdict ?? "—"}</td></tr>
              <tr><th>说明</th><td>{detail.reason ?? "—"}</td></tr>
              <tr><th>提交人</th><td>{detail.created_by}</td></tr>
            </tbody>
          </table>
        {:else}
          <p class="sub">加载中…</p>
        {/if}
        <button class="secondary" on:click={closeDetail}>关闭详情</button>
      </section>
    {/if}
  {/if}
</main>
