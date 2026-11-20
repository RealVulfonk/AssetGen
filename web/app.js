const $ = id => document.getElementById(id);
const state = { data: null, active: null, selected: new Set(), patch: {}, tag: '', jobSignature: '' };
let viewer;

function el(tag, text, className) {
  const node = document.createElement(tag);
  if (text !== undefined) node.textContent = text;
  if (className) node.className = className;
  return node;
}
function notify(message, error = false) {
  $('notification').textContent = message;
  $('notification').className = error ? 'error' : '';
  $('notification').hidden = false;
  clearTimeout(notify.timer); notify.timer = setTimeout(() => $('notification').hidden = true, 7000);
}
async function api(path, options) {
  const response = await fetch(path, options);
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || `HTTP ${response.status}`);
  return data;
}
function active() { return state.data?.assets.find(a => a.name === state.active); }
function filtered() {
  const query = $('search').value.toLowerCase();
  return state.data.assets.filter(a => a.name.includes(query) && (!$('category').value || a.category === $('category').value));
}
function updateSelection() {
  $('selected-count').textContent = `Выбрано: ${state.selected.size}`;
  const visible = filtered();
  const count = visible.filter(a => state.selected.has(a.name)).length;
  $('select-visible').checked = count > 0 && count === visible.length;
  $('select-visible').indeterminate = count > 0 && count < visible.length;
  const applicable = state.data.assets.filter(a => state.selected.has(a.name) && a.texture?.materials[state.tag]);
  $('scope').textContent = state.tag ? `Материал «${state.tag}» найден у ${applicable.length} из ${state.selected.size} выбранных моделей. Показаны параметры активной модели. Неизменённые поля у остальных сохранятся.` : 'Для модели нет рецепта текстуры.';
  $('generate').disabled = !applicable.length;
  $('generate').textContent = `Перегенерировать текстуры · ${applicable.length}`;
}
function renderList() {
  const list = $('assets'); list.replaceChildren();
  const assets = filtered(); $('count').textContent = `${assets.length} / ${state.data.assets.length}`;
  for (const asset of assets) {
    const row = el('div', undefined, `asset-row${state.active === asset.name ? ' active' : ''}`);
    const checkbox = el('input'); checkbox.type = 'checkbox'; checkbox.checked = state.selected.has(asset.name);
    checkbox.setAttribute('aria-label', `Выбрать ${asset.name}`);
    checkbox.addEventListener('click', e => e.stopPropagation());
    checkbox.addEventListener('change', () => { checkbox.checked ? state.selected.add(asset.name) : state.selected.delete(asset.name); updateSelection(); });
    row.append(checkbox);
    if (asset.preview) {
      const image = el('img'); image.src = `/asset/${asset.name}/preview_iso.png?v=${asset.version}`;
      image.alt = ''; image.loading = 'lazy'; row.append(image);
    } else row.append(el('div', '◇', 'thumb-placeholder'));
    const copy = el('div', undefined, 'asset-copy');
    copy.append(el('div', asset.name, 'asset-name'), el('div', asset.error ? 'Ошибка спеки' : !asset.built ? 'Не собрана' : asset.stale ? 'Геометрия устарела' : asset.textured ? 'С текстурой' : 'Без текстуры', 'asset-status'));
    row.append(copy); row.tabIndex = 0; row.setAttribute('role', 'button'); row.title = asset.name;
    row.addEventListener('click', () => activate(asset.name));
    row.addEventListener('keydown', e => { if (e.target === row && ['Enter', ' '].includes(e.key)) { e.preventDefault(); activate(asset.name); } });
    list.append(row);
  }
  if (!assets.length) list.append(el('p', 'Ничего не найдено', 'empty'));
  updateSelection();
}
function activate(name) {
  state.active = name; state.patch = {};
  const asset = active();
  $('asset-title').textContent = name;
  $('asset-meta').textContent = asset.error || `${asset.category} · ${asset.tris ?? '—'} треугольников · ${asset.tags.join(', ')}${asset.stale ? ' · требуется сборка геометрии' : ''}`;
  const tags = Object.keys(asset.texture?.materials || {});
  state.tag = tags.includes(state.tag) ? state.tag : tags.find(t => t !== 'default') || tags[0] || '';
  $('tag').replaceChildren(...tags.map(t => { const option = el('option', t); option.value = t; return option; }));
  $('tag').value = state.tag; $('tag').disabled = !tags.length;
  renderList(); renderEditor();
  if (viewer) viewer.load(asset);
  else for (const id of ['textured', 'solid']) $(id).querySelector('.view-message').textContent = '3D-просмотр недоступен. Для него нужен WebGL 2.';
}
function changed() {
  const count = Object.keys(state.patch).length;
  $('changes').textContent = count ? `Изменено полей: ${count}. Применятся к выбранным моделям.` : 'Без изменений: повторное запекание текущих рецептов.';
  $('reset').disabled = !count;
}
const labels = { palette: 'Палитра', brightness: 'Яркость', contrast: 'Контраст', contrast_pivot: 'Центр контраста',
  ao: 'Затемнение углублений', ao_distance: 'Радиус AO, м', edge: 'Выделение рёбер', roughness: 'Шероховатость',
  metallic: 'Металличность', opacity: 'Непрозрачность', scale: 'Частота рисунка', detail: 'Детализация зерна',
  distortion: 'Искажение волокон', direction: 'Направление', value: 'Тон', gradient: 'Переход палитры',
  staves: 'Количество клёпок', seam_width: 'Ширина стыка', lid_board_width: 'Ширина доски крышки, м', grain_strength: 'Выраженность волокон' };
function selectField(parent, name, choices, value, onChange) {
  const field = el('div', undefined, 'field');
  const label = el('label', name, 'field-label'); const select = el('select');
  select.id = `field-${name}`; label.htmlFor = select.id;
  for (const [key, text] of choices) { const option = el('option', text); option.value = key; select.append(option); }
  select.value = value;
  select.onchange = () => { label.classList.add('changed'); onChange(select.value); changed(); };
  field.append(label, select); parent.append(field); return select;
}
function numberField(parent, key, schema, value) {
  const field = el('div', undefined, 'field');
  const top = el('div', undefined, 'field-top');
  const label = el('label', labels[key] || key); label.htmlFor = `field-${key}`;
  const control = el('div', undefined, 'field-control');
  const input = el('input'); input.type = 'number'; input.id = `field-${key}`;
  const integer = schema.type === 'integer'; input.step = integer ? '1' : 'any';
  if (schema.minimum !== undefined) input.min = schema.minimum;
  if (schema.exclusiveMinimum !== undefined) input.min = schema.exclusiveMinimum + (integer ? 1 : Number.EPSILON);
  if (schema.maximum !== undefined) input.max = schema.maximum;
  input.value = value ?? schema.default ?? 0;
  const range = el('input'); range.type = 'range'; range.setAttribute('aria-label', labels[key] || key);
  range.min = input.min || '0'; range.max = input.max || String(Math.max(20, Number(input.value) * 2));
  range.step = integer ? '1' : '0.001'; range.value = input.value;
  const apply = v => { state.patch[key] = Number(v); label.classList.add('changed'); changed(); };
  input.oninput = () => { if (input.value !== '' && input.validity.valid) { range.value = input.value; apply(input.value); } };
  range.oninput = () => { input.value = range.value; apply(range.value); };
  if (key in state.patch) label.classList.add('changed');
  top.append(label); control.append(range, input); field.append(top, control); parent.append(field);
}
function renderEditor() {
  const container = $('editor-fields'); container.replaceChildren();
  const original = active()?.texture?.materials[state.tag];
  if (!original) { changed(); updateSelection(); return; }
  let config = { ...original, ...state.patch };
  if ('preset' in state.patch) {
    const common = state.data.schema.$defs.material_common.properties;
    config = Object.fromEntries(Object.entries(config).filter(([key]) => key in common || key === 'preset' || key in state.patch));
  }
  const section = el('div', undefined, 'editor-section'); section.append(el('h3', 'Рецепт поверхности')); container.append(section);
  const presets = ['noise', 'wood', 'coopered_wood', 'stone', 'flat', 'metal', 'bone', 'cloth'];
  const presetValue = config.layers ? 'layers' : config.preset || 'noise';
  const choices = presets.map(p => [p, p]);
  if (config.layers) choices.unshift(['layers', 'Собственные слои JSON']);
  selectField(section, 'Процедурный рисунок', choices, presetValue, value => {
    state.patch = { ...Object.fromEntries(Object.entries(state.patch).filter(([k]) => k in state.data.schema.$defs.material_common.properties)), preset: value };
    renderEditor();
  });
  section.append(el('p', 'Смена рецепта заменяет его специальные параметры. Выбор фактуры ниже сохраняет рисунок и стыки.', 'hint'));
  const palettes = Object.keys(state.data.palettes);
  const paletteChoices = palettes.map(p => [p, p]);
  if (Array.isArray(config.palette)) paletteChoices.unshift(['custom', 'Своя палитра JSON']);
  const paletteSelect = selectField(section, 'Палитра', paletteChoices, Array.isArray(config.palette) ? 'custom' : config.palette, value => {
    if (value !== 'custom') state.patch.palette = value;
    else delete state.patch.palette;
    swatches();
  });
  const colors = el('div', undefined, 'palette-preview'); section.append(colors);
  function swatches() { colors.replaceChildren(...(state.data.palettes[paletteSelect.value] || config.palette || []).map(color => { const swatch = el('span'); swatch.style.background = color; return swatch; })); }
  swatches();
  const imagesSection = el('div', undefined, 'editor-section'); imagesSection.append(el('h3', 'Фактура из изображения')); container.append(imagesSection);
  const source = state.patch.source_detail === null ? null : { ...original.source_detail, ...state.patch.source_detail };
  const imageChoices = [['', 'Только процедурный рисунок'], ...state.data.images.map(i => [i, i])];
  selectField(imagesSection, 'Исходник', imageChoices, source?.image || '', value => {
    state.patch.source_detail = value ? { ...state.patch.source_detail, image: value } : null;
    renderEditor();
  });
  const grid = el('div', undefined, 'image-grid');
  for (const image of state.data.images) {
    const button = el('button', undefined, `image-choice${source?.image === image ? ' active' : ''}`);
    const img = el('img'); img.src = `/textures/${image}`; img.alt = ''; img.loading = 'lazy';
    button.title = image; button.setAttribute('aria-label', `Фактура ${image}`);
    button.append(img, el('span', image.replace(/\.(png|jpe?g)$/, '')));
    button.onclick = () => { state.patch.source_detail = { ...state.patch.source_detail, image }; renderEditor(); };
    grid.append(button);
  }
  imagesSection.append(grid, el('p', 'Карта добавляет фактуру через яркость. Цвет задаётся палитрой. Результат обновится после запекания.', 'hint'));
  if (source?.image) {
    for (const [key, label, min, max, step, fallback] of [['tile_size', 'Размер повтора, м', 0.01, 100, 0.01, 1], ['strength', 'Влияние фактуры', 0, 1, 0.01, 0.6]]) {
      const field = el('div', undefined, 'field'); const text = el('label', label, 'field-label');
      const input = el('input'); input.type = 'number'; input.id = `source-${key}`; text.htmlFor = input.id;
      input.min = min; input.max = max; input.step = step; input.value = source[key] ?? fallback;
      input.oninput = () => { if (input.value !== '' && input.validity.valid) { state.patch.source_detail = { ...state.patch.source_detail, [key]: Number(input.value) }; text.classList.add('changed'); changed(); } };
      field.append(text, input); imagesSection.append(field);
    }
  }
  const settings = el('div', undefined, 'editor-section'); settings.append(el('h3', 'Параметры материала')); container.append(settings);
  const defs = state.data.schema.$defs;
  const recipe = defs.material.oneOf.find(x => x.properties?.preset?.const === presetValue) || defs.material.oneOf[0];
  const properties = { ...defs.material_common.properties, ...(config.layers ? {} : recipe.properties) };
  for (const [key, raw] of Object.entries(properties)) {
    if (['palette', 'source_detail', 'preset', 'layers'].includes(key)) continue;
    const schema = raw.$ref ? defs[raw.$ref.split('/').pop()] : raw;
    if (['number', 'integer'].includes(schema.type)) numberField(settings, key, schema, config[key]);
    else if (schema.enum) selectField(settings, labels[key] || key, schema.enum.map(v => [v, v]), config[key] ?? schema.default, value => { state.patch[key] = value; });
  }
  const advanced = el('details', undefined, 'editor-section'); advanced.append(el('summary', 'Текущий JSON материала'), el('pre', JSON.stringify(original, null, 2), 'job-error')); container.append(advanced);
  changed(); updateSelection();
}
async function loadCatalog(initial = false) {
  const data = await api('/api/catalog'); state.data = data;
  const selectedCategory = $('category').value;
  $('category').replaceChildren(new Option('Все категории', ''), ...[...new Set(data.assets.map(a => a.category))].sort().map(c => new Option(c, c)));
  $('category').value = selectedCategory;
  if (initial || !active()) {
    const first = data.assets.find(a => a.built && a.texture) || data.assets[0];
    if (first) { state.selected.add(first.name); activate(first.name); }
  } else { renderList(); }
}
const statusLabels = { queued: 'В очереди', running: 'Запекание…', done: 'Готово', error: 'Ошибка', skipped: 'Пропущено', interrupted: 'Прервано' };
async function pollJobs() {
  try {
    const jobs = await api('/api/jobs');
    const signature = JSON.stringify(jobs);
    if (signature !== state.jobSignature) {
      const hadJobs = Boolean(state.jobSignature); state.jobSignature = signature;
      $('jobs').replaceChildren();
      $('queue-count').textContent = jobs.length ? `Заданий: ${jobs.length}` : 'Нет заданий';
      for (const job of jobs) {
        const block = el('div', undefined, 'job');
        const head = el('div', undefined, 'job-header');
        head.append(el('span', `${job.tag} · ${job.items.length} моделей`), el('span', statusLabels[job.status])); block.append(head);
        for (const item of job.items) {
          const row = el('div', undefined, `job-item ${item.status}`);
          row.append(el('span', item.name), el('span', statusLabels[item.status]));
          if (item.error) row.append(el('pre', item.error, 'job-error'));
          block.append(row);
        }
        const details = el('details'); details.append(el('summary', 'Резервные копии'), el('p', `.workbench/jobs/${job.id}/<модель>/backup`, 'hint')); block.append(details);
        $('jobs').append(block);
      }
      if (!jobs.length) $('jobs').append(el('p', 'Очередь пуста. Запекание запускается по кнопке справа.', 'empty'));
      if (hadJobs && jobs.some(j => ['done', 'error'].includes(j.status))) {
        const previousVersion = active()?.version;
        await loadCatalog();
        if (active()?.version !== previousVersion) {
          viewer?.load(active());
          if (!Object.keys(state.patch).length) renderEditor();
        }
      }
    }
  } catch (error) { $('queue-count').textContent = `Нет связи: ${error.message}`; }
  finally { setTimeout(pollJobs, 1500); }
}
$('search').oninput = renderList; $('category').onchange = renderList;
$('select-visible').onchange = () => { for (const a of filtered()) $('select-visible').checked ? state.selected.add(a.name) : state.selected.delete(a.name); renderList(); };
$('clear-selection').onclick = () => { state.selected.clear(); renderList(); };
$('tag').onchange = () => { state.tag = $('tag').value; state.patch = {}; renderEditor(); };
$('reset').onclick = () => { state.patch = {}; renderEditor(); };
$('fit').onclick = () => viewer?.fit();
$('refresh').onclick = async () => { try { await loadCatalog(); if (active()) { viewer?.load(active()); renderEditor(); } } catch (error) { notify(error.message, true); } };
$('generate').onclick = async () => {
  if ([...document.querySelectorAll('.editor input')].some(input => !input.validity.valid || input.value === '')) { notify('Проверьте числовые значения параметров.', true); return; }
  $('generate').disabled = true;
  try {
    await api('/api/jobs', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ assets: [...state.selected], tag: state.tag, patch: state.patch }) });
    state.patch = {}; renderEditor(); notify('Задание добавлено в очередь. Можно продолжать просмотр.');
  } catch (error) { notify(error.message, true); }
  finally { updateSelection(); }
};
try {
  const { TwinViewer } = await import('./viewer.js'); viewer = new TwinViewer();
} catch (error) { notify(`3D-просмотр недоступен: ${error.message}`, true); }
try { await loadCatalog(true); pollJobs(); } catch (error) { notify(`Не удалось загрузить каталог: ${error.message}`, true); }
