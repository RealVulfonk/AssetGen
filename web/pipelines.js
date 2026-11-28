// The existing editor and bake queue keep their own state while panels switch.
export function initAdmin({ api, notify, openEditor }) {
  const $ = id => document.getElementById(id);
  const el = (tag, text, cls) => {
    const node = document.createElement(tag);
    if (text !== undefined) node.textContent = text;
    if (cls) node.className = cls;
    return node;
  };
  const labels = { queued: 'В очереди', running: 'Обработка', needs_review: 'Нужен просмотр', error: 'Ошибка', interrupted: 'Прервано' };
  const channels = [['base_color', 'Base Color'], ['normal', 'Normal'], ['roughness', 'Roughness']];
  let runs = [], selectedId = '', signature = '', channel = 'base_color', zoom = 0.5, borders = false, compareWith = 'split';
  let polling = false;
  function navigate(panel, id = '') { location.hash = panel === 'runs' && id ? `runs/${id}` : panel; }
  function showPanel() {
    const [requested, id] = location.hash.slice(1).split('/');
    const panel = ['editor', 'pipelines', 'runs'].includes(requested) ? requested : 'editor';
    for (const name of ['editor', 'pipelines', 'runs']) $(`panel-${name}`).hidden = name !== panel;
    for (const button of document.querySelectorAll('nav [data-panel]')) button.classList.toggle('active', button.dataset.panel === panel);
    if (id && id !== selectedId) { selectedId = id; renderHistory(); renderDetail(); }
    if (panel === 'runs') poll();
    window.dispatchEvent(new Event('resize'));
  }
  for (const button of document.querySelectorAll('[data-panel]')) button.onclick = () => navigate(button.dataset.panel);
  window.addEventListener('hashchange', showPanel);
  $('intake-form').onsubmit = async event => {
    event.preventDefault();
    if ($('intake-submit').disabled) return;
    const file = $('intake-file').files[0];
    if (!file) return;
    if (file.size > 40 * 1024 * 1024) { notify('Файл превышает 40 МиБ.', true); return; }
    $('intake-submit').disabled = true; $('intake-message').textContent = 'Загрузка файла…';
    try {
      const params = new URLSearchParams({ name: $('intake-name').value, band: $('intake-band').value, filename: file.name });
      const result = await api(`/api/pipelines/pbr_intake?${params}`, { method: 'POST', headers: { 'Content-Type': 'application/octet-stream' }, body: file });
      $('intake-message').textContent = 'Файл сохранён. Подготовка добавлена в очередь.';
      selectedId = result.id; navigate('runs', result.id); await poll();
    } catch (error) { $('intake-message').textContent = error.message; notify(error.message, true); }
    finally { $('intake-submit').disabled = false; }
  };
  function link(run, selection, filename, label) {
    const node = el('a', label || filename); node.href = `/run-file/${run.id}/${selection}/${filename}`; node.target = '_blank'; node.rel = 'noopener'; return node;
  }
  function renderHistory() {
    const list = $('run-list'); list.replaceChildren();
    for (const run of runs) {
      const button = el('button', undefined, `run-choice${run.id === selectedId ? ' active' : ''}`);
      button.append(el('strong', run.name), el('span', `${run.band} px · ${labels[run.status] || run.status}`), el('small', new Date(run.created * 1000).toLocaleString()));
      button.onclick = () => { selectedId = run.id; navigate('runs', run.id); renderHistory(); renderDetail(); };
      list.append(button);
    }
    if (!runs.length) list.append(el('p', 'Запусков пока нет.', 'empty'));
  }
  function renderComparison(run, parent) {
    const section = el('section', undefined, 'comparison');
    section.append(el('h2', 'Сравнение поверхностей · повтор 2 × 2'));
    const controls = el('div', undefined, 'comparison-controls');
    const channelLabel = el('label', 'Канал'); const channelSelect = el('select'); channelSelect.id = 'compare-channel';
    for (const [value, title] of channels) channelSelect.append(new Option(title, value));
    channelSelect.value = channel; channelLabel.append(channelSelect);
    const zoomLabel = el('label', 'Общий масштаб'); const slider = el('input'); slider.id = 'compare-zoom'; slider.type = 'range'; slider.min = '0.1'; slider.max = '4'; slider.step = '0.05'; slider.value = zoom;
    const zoomValue = el('span'); zoomLabel.append(slider, zoomValue);
    const boundsLabel = el('label', 'Показать жёлтые линии стыка'); const bounds = el('input'); bounds.id = 'compare-borders'; bounds.type = 'checkbox'; bounds.checked = borders; boundsLabel.prepend(bounds);
    const baselineLabel = el('label', 'Слева'); const baseline = el('select'); baseline.id = 'compare-baseline'; baseline.append(new Option('Исходный split', 'split'));
    addBaselines(baseline, run);
    if (![...baseline.options].some(option => option.value === compareWith)) compareWith = 'split';
    baseline.value = compareWith; baselineLabel.append(baseline);
    baseline.onchange = () => { compareWith = baseline.value; renderDetail(); };
    const seamButton = el('button', 'Показать стык'); seamButton.type = 'button'; seamButton.id = 'compare-center';
    controls.append(baselineLabel, channelLabel, zoomLabel, boundsLabel, seamButton); section.append(controls);
    const pair = el('div', undefined, 'comparison-pair'); const planes = [], ports = [];
    const comparisonRun = runs.find(item => item.id === compareWith);
    for (const [imageRun, selection, title] of [[comparisonRun || run, comparisonRun ? 'candidate' : 'split', comparisonRun ? `Кандидат · ${comparisonRun.band} px` : 'Исходный split'], [run, 'candidate', `Кандидат · ${run.band} px`]]) {
      const column = el('div'); column.append(el('h3', title));
      if (selection === 'candidate' && imageRun.status !== 'needs_review') { column.append(el('p', 'Кандидат недоступен. Исходный split сохранён.', 'hint')); pair.append(column); continue; }
      const port = el('div', undefined, 'repeat-viewport'); port.tabIndex = 0; port.setAttribute('aria-label', `${title}, повтор 2 на 2; прокрутка синхронизирована`);
      const plane = el('div', undefined, 'repeat-plane'); port.append(plane); column.append(port); pair.append(column); planes.push([plane, imageRun, selection]); ports.push(port);
      port.addEventListener('scroll', () => { for (const other of ports) if (other !== port && (Math.abs(other.scrollLeft - port.scrollLeft) > 1 || Math.abs(other.scrollTop - port.scrollTop) > 1)) { other.scrollLeft = port.scrollLeft; other.scrollTop = port.scrollTop; } });
    }
    function update() {
      const width = run.size[0] / 3 * zoom, height = run.size[1] * zoom;
      for (const [plane, imageRun, selection] of planes) {
        plane.style.width = `${width * 2}px`; plane.style.height = `${height * 2}px`;
        plane.style.backgroundImage = `url("/run-file/${imageRun.id}/${selection}/${imageRun.name}_${channel}.png")`;
        plane.style.backgroundSize = `${width}px ${height}px`; plane.classList.toggle('borders', borders);
      }
      zoomValue.textContent = `${Math.round(zoom * 100)}%`;
    }
    function centerSeam() {
      for (const port of ports) {
        port.scrollLeft = Math.max(0, (port.scrollWidth - port.clientWidth) / 2);
        port.scrollTop = Math.max(0, (port.scrollHeight - port.clientHeight) / 2);
      }
    }
    seamButton.onclick = centerSeam;
    channelSelect.onchange = () => { channel = channelSelect.value; update(); };
    slider.oninput = () => { zoom = Number(slider.value); update(); centerSeam(); };
    bounds.onchange = () => { borders = bounds.checked; update(); };
    update(); section.append(pair, el('p', 'Приближение и прокрутка связаны. Рисунок оценивается вручную; удачная метрика не означает художественную приёмку.', 'hint')); parent.append(section);
    requestAnimationFrame(centerSeam);
  }
  function renderDetail() {
    const parent = $('run-detail'); parent.replaceChildren();
    const run = runs.find(item => item.id === selectedId);
    if (!run) { parent.append(el('p', runs.length ? 'Выберите запуск.' : 'Загрузите лист в разделе «Пайплайны».', 'empty')); return; }
    parent.append(el('h2', `${run.name} · ${labels[run.status] || run.status}`), el('p', `${run.filename} · ${run.size.join(' × ')} · полоса ${run.band} px · этап ${run.stage}`, 'hint'));
    parent.append(el('p', `ID: ${run.id}${run.source_run ? ` · split из ${run.source_run}` : ''}`, 'hint'));
    if (run.previous) { const previous = el('button', 'Предыдущий запуск'); previous.onclick = () => { selectedId = run.previous; navigate('runs', selectedId); renderHistory(); renderDetail(); }; parent.append(previous); }
    if (run.error) parent.append(el('pre', run.error, 'pipeline-error'));
    const files = el('div', undefined, 'result-files');
    const original = link(run, 'input', 'source', 'Скачать загруженный исходник');
    original.download = run.filename || 'source';
    files.append(original);
    if (run.split_ready) {
      for (const [role, title] of channels) files.append(link(run, 'split', `${run.name}_${role}.png`, `Split · ${title}`));
      if (run.status === 'needs_review') {
        for (const [role, title] of channels) files.append(link(run, 'candidate', `${run.name}_${role}.png`, `Кандидат · ${title}`));
        files.append(link(run, 'candidate', 'report.json', 'Отчёт обработки'));
      }
      renderComparison(run, parent);
    }
    parent.append(files);
    const variant = el('form', undefined, 'variant-form'); const bandLabel = el('label', 'Другая ширина, px');
    const band = el('input'); band.type = 'number'; band.min = 1; band.max = 4096; band.value = run.band; band.required = true; bandLabel.append(band);
    const variantButton = el('button', run.split_ready ? 'Сравнить другую ширину' : 'Повторить сохранённый вход'); variantButton.disabled = ['queued', 'running'].includes(run.status); variant.append(bandLabel, variantButton);
    variant.onsubmit = async event => {
      event.preventDefault(); variantButton.disabled = true;
      try { const result = await api('/api/runs/variant', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ id: run.id, band: Number(band.value) }) }); selectedId = result.id; navigate('runs', result.id); await poll(); }
      catch (error) { notify(error.message, true); variantButton.disabled = false; }
    }; parent.append(variant);
    if (run.split_ready) {
      const form = el('form', undefined, 'publication-form'); form.append(el('h3', 'Опубликовать выбранный комплект в библиотеку'));
      form.append(el('p', 'Публикуются все три карты под новым свободным именем. Существующие поверхности не заменяются. Публикация не означает Godot-приёмку.', 'hint'));
      const sourceLabel = el('label', 'Комплект'); const source = el('select'); source.id = 'publish-selection'; source.append(new Option('Исходный split', 'split'));
      if (run.status === 'needs_review') source.append(new Option(`Кандидат · ${run.band} px`, 'candidate'));
      sourceLabel.append(source); const nameLabel = el('label', 'Свободное имя'); const name = el('input'); name.id = 'publish-name'; name.pattern = '[a-z][a-z0-9]*(_[a-z0-9]+)*'; name.maxLength = 80; name.required = true; name.value = run.name; nameLabel.append(name);
      const button = el('button', 'Опубликовать комплект'); const message = el('p', '', 'hint'); message.setAttribute('role', 'status'); form.append(sourceLabel, nameLabel, button, message);
      form.onsubmit = async event => {
        event.preventDefault(); button.disabled = true;
        try { await api('/api/runs/publish', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ id: run.id, selection: source.value, name: name.value }) }); notify(`Опубликован комплект ${name.value}`); await poll(); }
        catch (error) { message.textContent = error.message; notify(error.message, true); }
        finally { button.disabled = false; }
      }; parent.append(form);
    }
    for (const receipt of run.publications || []) {
      const block = el('p', `${receipt.name} · ${receipt.selection} · ${receipt.status}`, 'hint');
      if (receipt.status === 'published') {
        const button = el('button', 'Применить в редакторе'); button.onclick = async () => { try { await openEditor(receipt.name); navigate('editor'); } catch (error) { notify(error.message, true); } }; block.append(button);
      } parent.append(block);
    }
    const log = el('details'); log.open = ['error', 'interrupted'].includes(run.status); log.append(el('summary', 'История этапов и сообщения'));
    for (const event of run.events) log.append(el('pre', `${new Date(event.time * 1000).toLocaleTimeString()} · ${event.stage}\n${event.message}`, 'pipeline-log')); parent.append(log);
  }
  function addBaselines(select, run) {
    const sourceId = run.source_run || run.id;
    const existing = new Set([...select.options].map(option => option.value));
    for (const other of runs) {
      if (other.id !== run.id && other.status === 'needs_review' && !existing.has(other.id) && (other.source_run || other.id) === sourceId) {
        select.append(new Option(`Кандидат ${other.band} px · ${new Date(other.created * 1000).toLocaleTimeString()}`, other.id));
      }
    }
  }
  async function poll() {
    if ($('panel-runs').hidden || polling) return;
    polling = true;
    try {
      const data = await api('/api/runs');
      const next = JSON.stringify(data);
      if (next === signature) return;
      const previous = runs.find(item => item.id === selectedId);
      signature = next;
      runs = data;
      if (!selectedId && runs.length) selectedId = runs[0].id;
      renderHistory();
      const current = runs.find(item => item.id === selectedId);
      if (!previous || JSON.stringify(previous) !== JSON.stringify(current)) renderDetail();
      else if ($('compare-baseline')) addBaselines($('compare-baseline'), current);
    } catch (error) {
      signature = '';
      $('run-list').textContent = `Нет связи: ${error.message}`;
    } finally { polling = false; }
  }
  api('/api/pipelines').then(definitions => {
    if (!definitions.some(definition => definition.id === 'pbr_intake')) throw new Error('На сервере недоступна подготовка PBR. Перезапустите workbench.py и обновите страницу.');
    $('intake-submit').disabled = false;
    for (const definition of definitions) { const p = el('p', `${definition.title}: ${definition.description}`, 'hint'); $('pipeline-definitions').append(p); }
  }).catch(error => {
    $('intake-message').textContent = error.status === 404
      ? 'Запущена старая версия мастерской. Перезапустите workbench.py и обновите страницу.'
      : `Не удалось подключить подготовку PBR. ${error.message}`;
  });
  showPanel(); setInterval(poll, 1500);
}
