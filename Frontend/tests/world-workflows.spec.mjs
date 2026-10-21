import { test as base, expect } from 'playwright/test';

// Requests stay in the browser fixture: these tests never touch an author's database.
const test = base.extend({
  world: async ({ page }, provideWorld) => {
    const chapter = { id: 'ch1', chapter_number: 1, title: 'The Crossing', content: 'Arin crossed Silver Haven to meet Mira.\n\nThe treaty was signed at dawn.', word_count: 14 };
    const entities = [
      { id: 'arin', canonical_name: 'Arin', entity_type: 'character' },
      { id: 'mira', canonical_name: 'Mira', entity_type: 'character' },
      { id: 'legacy-event', canonical_name: 'Legacy event entity', entity_type: 'event' },
    ].map(item => ({ ...item, world_id: 'w1', aliases: [], facts: [] }));
    const events = [1, 2].map(number => ({ id: `ev${number}`, world_id: 'w1', chapter_id: 'ch1', chapter_number: 1, event_type: 'MEETING', description: `Real timeline event ${number}`, participants: [], sequence_index: number }));
    const state = { entities, events, relationships: [], writes: [], graphReads: 0, failNextEntity: false, failNextEntityUpdate: false, failNextRelationship: false, failNextEvent: false };
    await page.addInitScript(() => localStorage.setItem('orion_token', 'browser-test-token'));
    await page.route('**/api/v1/**', async route => {
      const request = route.request();
      const path = new URL(request.url()).pathname.replace('/api/v1', '');
      const method = request.method();
      const json = request.postDataJSON();
      const reply = (body, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });
      if (method !== 'GET') state.writes.push({ path, method, json });
      if (path === '/auth/me') return reply({ id: 'author', email: 'test@example.com' });
      if (path === '/worlds') return reply([{ id: 'w1', name: 'Test World', stats: {} }]);
      if (path === '/worlds/w1/contradictions') return reply([]);
      if (path === '/worlds/w1/manuscripts') return reply([{ id: 'ms1', title: 'Test Manuscript' }]);
      if (path === '/worlds/w1/manuscripts/ms1/chapters') return reply([chapter]);
      if (path === '/worlds/w1/chapters/ch1') return reply(chapter);
      if (path === '/worlds/w1/entities' && method === 'GET') return reply(state.entities);
      if (path === '/worlds/w1/chat' && method === 'POST') return reply({
        response: json.entity_focus ? 'I will protect Nandivan.' : 'Your world contains Arin and Mira.',
        citations: [], suggested_actions: [],
      });
      if (path === '/worlds/w1/entities' && method === 'POST') {
        if (state.failNextEntity) { state.failNextEntity = false; return reply({ detail: 'Entity could not be saved' }, 400); }
        const entity = { id: `entity-${state.entities.length}`, world_id: 'w1', ...json, aliases: json.aliases || [], facts: [] };
        state.entities.push(entity);
        return reply(entity, 201);
      }
      if (path.startsWith('/worlds/w1/entities/') && method === 'PUT') {
        if (state.failNextEntityUpdate) { state.failNextEntityUpdate = false; return reply({ detail: 'Description could not be saved' }, 400); }
        const entity = state.entities.find(item => item.id === path.split('/').at(-1));
        if (json.canonical_name !== undefined) entity.canonical_name = json.canonical_name;
        if (json.entity_type !== undefined) entity.entity_type = json.entity_type;
        for (const [property, value] of Object.entries(json.attributes || {})) {
          let fact = entity.facts.find(item => item.property_name === property);
          if (!fact) { fact = { id: `${entity.id}-${property}`, property_name: property }; entity.facts.push(fact); }
          fact.current_version = { id: `version-${state.writes.length}`, value, status: 'ACTIVE', chapter_id: null };
        }
        return reply(entity);
      }
      if (path.startsWith('/worlds/w1/entities/') && method === 'GET') {
        const id = path.split('/').at(-1);
        const entity = state.entities.find(item => item.id === id);
        const relationships = state.relationships.filter(item => item.source_entity_id === id || item.target_entity_id === id).map(item => {
          const outgoing = item.source_entity_id === id;
          const other = state.entities.find(ent => ent.id === (outgoing ? item.target_entity_id : item.source_entity_id));
          return { id: item.id, targetId: other.id, targetName: other.canonical_name, targetType: other.entity_type, relation: item.relationship_type, direction: outgoing ? 'outgoing' : 'incoming', chapter_id: item.chapter_id, chapter_number: item.chapter_id ? 1 : null };
        });
        return reply({ ...entity, relationships, appearances: [] });
      }
      if (path === '/worlds/w1/timeline') return reply({ events: state.events, total: state.events.length });
      if (path === '/worlds/w1/events' && method === 'POST') {
        if (state.failNextEvent) { state.failNextEvent = false; return reply({ detail: 'Event could not be saved' }, 400); }
        const event = { id: `event-${state.events.length}`, world_id: 'w1', ...json, chapter_number: 1, participants: [] };
        state.events.push(event);
        return reply(event, 201);
      }
      if (path === '/worlds/w1/relationships' && method === 'POST') {
        if (state.failNextRelationship) { state.failNextRelationship = false; return reply({ detail: 'Relationship could not be saved' }, 400); }
        const relationship = { id: `relation-${state.writes.length}`, ...json };
        state.relationships.push(relationship);
        return reply(relationship, 201);
      }
      if (path.startsWith('/worlds/w1/relationships/') && method === 'DELETE') {
        state.relationships = state.relationships.filter(item => item.id !== path.split('/').at(-1));
        return route.fulfill({ status: 204 });
      }
      if (path === '/worlds/w1/graph') {
        state.graphReads++;
        return reply({ nodes: state.entities.map(item => ({ id: item.id, label: item.canonical_name, type: item.entity_type, degree: state.relationships.filter(rel => rel.source_entity_id === item.id || rel.target_entity_id === item.id).length })), edges: state.relationships.map(item => ({ id: item.id, source: item.source_entity_id, target: item.target_entity_id, type: item.relationship_type })) });
      }
      return reply({ detail: `Unexpected test request: ${method} ${path}` }, 404);
    });
    await provideWorld(state);
  },
});

const sidebar = page => page.getByRole('navigation', { name: 'World navigation' });
const openEntity = async page => {
  await page.getByRole('heading', { name: 'Arin', exact: true }).click();
  await page.getByRole('button', { name: 'Relations', exact: true }).click();
};
const selectText = async (page, text) => {
  await page.locator('.prose').evaluate((element, phrase) => {
    const walker = document.createTreeWalker(element, NodeFilter.SHOW_TEXT);
    const nodes = [];
    while (walker.nextNode()) nodes.push(walker.currentNode);
    const all = nodes.map(node => node.textContent).join('');
    const start = all.indexOf(phrase);
    if (start < 0) throw new Error(`Missing selection text: ${phrase}`);
    const range = document.createRange();
    let offset = 0;
    for (const node of nodes) {
      const end = offset + node.textContent.length;
      if (start >= offset && start < end) range.setStart(node, start - offset);
      if (start + phrase.length > offset && start + phrase.length <= end) { range.setEnd(node, start + phrase.length - offset); break; }
      offset = end;
    }
    window.getSelection().removeAllRanges();
    window.getSelection().addRange(range);
    document.dispatchEvent(new Event('selectionchange'));
  }, text);
};

test('assistant navigation opens character chat, sends the selected character, and survives reload', async ({ page, world }) => {
  await page.goto('/worlds/w1/world');
  await sidebar(page).getByRole('link', { name: 'AI Assistant', exact: true }).click();
  await expect(page).toHaveURL(/\/worlds\/w1\/assistant$/);
  await expect(page.getByRole('navigation', { name: 'Breadcrumb' })).toContainText('AI Assistant');
  await expect(sidebar(page).getByRole('link', { name: 'AI Assistant', exact: true })).toHaveAttribute('aria-current', 'page');
  const talkTo = page.getByRole('combobox', { name: /Talk to/ });
  await talkTo.selectOption('arin');
  await expect(page.getByRole('heading', { name: 'Talking to Arin', exact: true })).toBeVisible();
  await expect(talkTo.getByRole('option', { name: 'Legacy event entity' })).toHaveCount(0);
  const characterInput = page.getByPlaceholder('Ask Arin what they would do...');
  await characterInput.fill('What would you do next?');
  await characterInput.press('Enter');
  await expect(page.getByText('I will protect Nandivan.', { exact: true })).toBeVisible();
  expect(world.writes.at(-1)).toMatchObject({
    path: '/worlds/w1/chat', method: 'POST', json: { entity_focus: 'arin', message: 'What would you do next?' },
  });

  await talkTo.selectOption('');
  const worldInput = page.getByPlaceholder('Ask Orion about your manuscripts...');
  await worldInput.fill('Who lives here?');
  await worldInput.press('Enter');
  await expect(page.getByText('Your world contains Arin and Mira.', { exact: true })).toBeVisible();
  expect(world.writes.at(-1).json.entity_focus).toBeNull();
  await page.reload();
  await expect(page).toHaveURL(/\/worlds\/w1\/assistant$/);
  await expect(page.getByRole('heading', { name: 'Orion Assistant', exact: true })).toBeVisible();
  await expect(talkTo.getByRole('option', { name: 'Arin', exact: true })).toHaveCount(1);
});

test('ledger uses timeline counts, removes event forging, and links to Timeline', async ({ page, world }) => {
  await page.goto('/worlds/w1/world');
  await expect(page.getByRole('button', { name: /Events 2/ })).toBeVisible();
  await page.getByRole('button', { name: 'Forge Entity', exact: true }).click();
  await expect(page.getByRole('button', { name: /^Event\b/ })).toHaveCount(0);
  await expect(page.getByText('Create and manage events in the Timeline section.')).toBeVisible();
  await page.getByRole('button', { name: 'Close Drawer' }).click();
  await page.getByRole('button', { name: /Events 2/ }).click();
  await expect(page).toHaveURL(/\/timeline$/);
  expect(world.writes).toHaveLength(0);
});

test('authors can edit, cancel, save, reload, and clear an entity description', async ({ page, world }) => {
  world.entities[0].aliases = ['The Prince'];
  world.entities[0].facts = [{ id: 'description-arin', property_name: 'description', current_version: { value: 'Original synopsis.', status: 'ACTIVE' } }];
  await page.goto('/worlds/w1/world');
  await page.getByRole('heading', { name: 'Arin', exact: true }).click();
  await page.getByRole('button', { name: 'Edit description', exact: true }).click();
  await expect(page.getByLabel('Entity description', { exact: true })).toHaveValue('Original synopsis.');
  await page.getByLabel('Entity description', { exact: true }).fill('Discard this draft.');
  await page.getByRole('button', { name: 'Cancel', exact: true }).click();
  expect(world.writes).toHaveLength(0);
  await page.getByRole('button', { name: 'Edit description', exact: true }).click();
  await expect(page.getByLabel('Entity description', { exact: true })).toHaveValue('Original synopsis.');
  await page.getByLabel('Entity description', { exact: true }).fill('The author’s new synopsis.\nA second paragraph.');
  await page.getByRole('button', { name: 'Save description', exact: true }).click();
  await expect(page.getByLabel('Entity description', { exact: true })).toHaveCount(0);
  expect(world.writes.at(-1)).toMatchObject({ method: 'PUT', path: '/worlds/w1/entities/arin', json: { attributes: { description: 'The author’s new synopsis.\nA second paragraph.' } } });
  expect(Object.keys(world.writes.at(-1).json.attributes)).toEqual(['description']);
  await page.reload();
  await page.getByRole('heading', { name: 'Arin', exact: true }).click();
  await page.getByRole('button', { name: 'Edit description', exact: true }).click();
  await expect(page.getByLabel('Entity description', { exact: true })).toHaveValue('The author’s new synopsis.\nA second paragraph.');
  await page.getByLabel('Entity description', { exact: true }).fill('');
  await page.getByRole('button', { name: 'Save description', exact: true }).click();
  await expect(page.getByLabel('Entity description', { exact: true })).toHaveCount(0);
  await page.reload();
  await page.getByRole('heading', { name: 'Arin', exact: true }).click();
  await page.getByRole('button', { name: 'Edit description', exact: true }).click();
  await expect(page.getByLabel('Entity description', { exact: true })).toHaveValue('');
});

test('a failed description save preserves the draft and supports retry', async ({ page, world }) => {
  await page.goto('/worlds/w1/world');
  await page.getByRole('heading', { name: 'Arin', exact: true }).click();
  await page.getByRole('button', { name: 'Edit description', exact: true }).click();
  await page.getByLabel('Entity description', { exact: true }).fill('Unsaved synopsis.');
  world.failNextEntityUpdate = true;
  await page.getByRole('button', { name: 'Save description', exact: true }).click();
  await expect(page.getByRole('alert')).toHaveText('Description could not be saved');
  await expect(page.getByLabel('Entity description', { exact: true })).toHaveValue('Unsaved synopsis.');
  expect(world.entities[0].facts).toHaveLength(0);
  await page.getByRole('button', { name: 'Save description', exact: true }).click();
  await expect(page.getByLabel('Entity description', { exact: true })).toHaveCount(0);
  expect(world.entities[0].facts[0].current_version.value).toBe('Unsaved synopsis.');
});

test('entity card creates both directions, reports save errors, and deletes relations', async ({ page, world }) => {
  await page.goto('/worlds/w1/world');
  await openEntity(page);
  await page.getByRole('button', { name: 'Add Relationship', exact: true }).click();
  await page.getByLabel('Related entity').selectOption('mira');
  await page.getByLabel('Relationship type', { exact: true }).fill('mentor of');
  await page.getByLabel('Relationship chapter').selectOption('ch1');
  world.failNextRelationship = true;
  await page.getByRole('button', { name: 'Create Relationship', exact: true }).click();
  await expect(page.getByRole('alert')).toHaveText('Relationship could not be saved');
  await page.getByRole('button', { name: 'Create Relationship', exact: true }).click();
  await expect(page.getByText('MENTOR OF', { exact: true })).toBeVisible();
  expect(world.relationships[0]).toMatchObject({ source_entity_id: 'arin', target_entity_id: 'mira', relationship_type: 'MENTOR_OF', chapter_id: 'ch1' });
  await page.getByRole('button', { name: 'Add Relationship', exact: true }).click();
  await page.getByLabel('Relationship direction').selectOption('incoming');
  await page.getByLabel('Related entity').selectOption('mira');
  await page.getByLabel('Relationship type', { exact: true }).fill('KNOWS');
  await page.getByRole('button', { name: 'Create Relationship', exact: true }).click();
  await expect(page.getByText('2 connections', { exact: true })).toBeVisible();
  expect(world.relationships[1]).toMatchObject({ source_entity_id: 'mira', target_entity_id: 'arin' });
  page.once('dialog', dialog => dialog.dismiss());
  await page.getByRole('button', { name: 'Delete relationship with Mira' }).first().click();
  expect(world.relationships).toHaveLength(2);
  page.once('dialog', dialog => dialog.accept());
  await page.getByRole('button', { name: 'Delete relationship with Mira' }).first().click();
  await expect(page.getByText('1 connection', { exact: true })).toBeVisible();
  expect(world.relationships).toHaveLength(1);
});

test('failed forging keeps the form open and retries through the entity endpoint', async ({ page, world }) => {
  await page.goto('/worlds/w1/world');
  await page.getByRole('button', { name: 'Forge Entity', exact: true }).click();
  await page.getByPlaceholder('e.g. Valerius Thorne', { exact: true }).fill('New Hero');
  await page.getByPlaceholder('Provide background lore, significance, attributes, or historical context...', { exact: true }).fill('A new ally.');
  world.failNextEntity = true;
  await page.locator('button[form="forge-entity-form"]').click();
  await expect(page.getByRole('alert')).toHaveText('Entity could not be saved');
  await expect(page.getByPlaceholder('e.g. Valerius Thorne', { exact: true })).toHaveValue('New Hero');
  await page.locator('button[form="forge-entity-form"]').click();
  await expect(page.getByRole('heading', { name: 'Forge New Entity', exact: true })).toHaveCount(0);
  expect(world.entities.at(-1)).toMatchObject({ canonical_name: 'New Hero', entity_type: 'character' });
});

test('graph drag creates directed relations after zoom and refreshes card mutations', async ({ page, world }) => {
  await page.goto('/worlds/w1/graph');
  const source = page.getByRole('button', { name: 'Drag relationship from Arin', exact: true });
  const target = page.locator('[data-node-id="mira"]');
  await expect(source).toBeVisible();
  await page.getByRole('button', { name: 'Zoom Out (-)', exact: true }).click();
  await page.keyboard.press('ArrowRight');
  await page.keyboard.press('ArrowDown');
  const from = await source.boundingBox();
  const to = await target.boundingBox();
  await page.mouse.move(from.x + from.width / 2, from.y + from.height / 2);
  await page.mouse.down();
  await page.mouse.move(to.x + to.width / 2, to.y + to.height / 2, { steps: 12 });
  await expect(page.locator('line[marker-end="url(#arrow-draft)"]')).toBeVisible();
  await page.mouse.up();
  await expect(page.getByLabel('Source entity', { exact: true })).toHaveValue('arin');
  await expect(page.getByLabel('Target entity', { exact: true })).toHaveValue('mira');
  await page.getByRole('button', { name: 'Create Relationship', exact: true }).click();
  await expect(page.getByLabel('Source entity', { exact: true })).toHaveCount(0);
  await expect(page.locator('svg').getByText('ALLY OF', { exact: true })).toBeVisible();
  const before = world.graphReads;
  await page.locator('[data-node-id="arin"]').click();
  await page.getByRole('button', { name: 'Relations', exact: true }).click();
  page.once('dialog', dialog => dialog.accept());
  await page.getByRole('button', { name: 'Delete relationship with Mira' }).click();
  await expect.poll(() => world.graphReads).toBeGreaterThan(before);
  await expect(page.getByText('No Active Relationships', { exact: true })).toBeVisible();
  expect(world.relationships).toHaveLength(0);
});

test('graph cancels self connections and Esc without saving', async ({ page, world }) => {
  await page.goto('/worlds/w1/graph');
  const source = page.getByRole('button', { name: 'Drag relationship from Arin', exact: true });
  await expect(source).toBeVisible();
  const from = await source.boundingBox();
  await page.mouse.move(from.x + from.width / 2, from.y + from.height / 2);
  await page.mouse.down();
  await page.mouse.move(from.x + from.width / 2 - 30, from.y + from.height / 2);
  await page.mouse.up();
  await expect(page.getByLabel('Source entity', { exact: true })).toHaveCount(0);
  await page.mouse.move(from.x + from.width / 2, from.y + from.height / 2);
  await page.mouse.down();
  await page.keyboard.press('Escape');
  await page.mouse.up();
  await expect(page.locator('line[marker-end="url(#arrow-draft)"]')).toHaveCount(0);
  expect(world.writes).toHaveLength(0);
});

test('chapter selection creates entities, locations, and chapter-linked timeline events', async ({ page, world }) => {
  await page.goto('/worlds/w1/manuscripts/ms1');
  await expect(page.locator('.prose')).toContainText('Silver Haven');
  await selectText(page, 'Silver Haven');
  await page.getByRole('button', { name: 'Create location', exact: true }).click();
  await page.getByRole('dialog').getByRole('button', { name: 'Create location', exact: true }).click();
  await expect(page.getByRole('status')).toContainText('Location saved');
  expect(world.entities.at(-1)).toMatchObject({ canonical_name: 'Silver Haven', entity_type: 'location' });
  await selectText(page, 'The treaty');
  await page.getByRole('button', { name: 'Create entity', exact: true }).click();
  await page.getByLabel('Entity type', { exact: true }).selectOption('object');
  await page.getByRole('dialog').getByRole('button', { name: 'Create entity', exact: true }).click();
  await expect(page.getByRole('status')).toContainText('Entity saved');
  expect(world.entities.at(-1)).toMatchObject({ canonical_name: 'The treaty', entity_type: 'object' });
  await selectText(page, 'The treaty was signed at dawn.');
  await page.getByRole('button', { name: 'Create event', exact: true }).click();
  world.failNextEvent = true;
  await page.getByRole('dialog').getByRole('button', { name: 'Create event', exact: true }).click();
  await expect(page.getByRole('alert')).toHaveText('Event could not be saved');
  await page.getByRole('dialog').getByRole('button', { name: 'Create event', exact: true }).click();
  await expect(page.getByRole('status')).toContainText('Event saved to Timeline');
  expect(world.events.at(-1)).toMatchObject({ chapter_id: 'ch1', description: 'The treaty was signed at dawn.' });
  expect(world.writes.filter(item => item.path.endsWith('/entities'))).toHaveLength(2);
  await sidebar(page).getByRole('link', { name: /World Ledger/ }).click();
  await expect(page.getByRole('button', { name: /Events 3/ })).toBeVisible();
});

test('chapter editor selection works in edit mode and navigation names the active page', async ({ page, world }) => {
  await page.goto('/worlds/w1/manuscripts/ms1');
  await expect(page.getByRole('navigation', { name: 'Breadcrumb' })).toContainText('Chapter Editor');
  await expect(sidebar(page).getByRole('link', { name: /Manuscripts/ })).toHaveAttribute('aria-current', 'page');
  await expect(page).toHaveTitle(/Chapter Editor/);
  await page.getByRole('button', { name: 'Edit Text', exact: true }).click();
  await page.locator('article textarea').evaluate(element => { element.focus(); element.setSelectionRange(0, 4); document.dispatchEvent(new Event('selectionchange')); });
  await page.getByRole('button', { name: 'Create entity', exact: true }).click();
  await expect(page.getByRole('dialog').getByLabel('Name', { exact: true })).toHaveValue('Arin');
  await page.getByRole('dialog').getByRole('button', { name: 'Cancel', exact: true }).click();
  await sidebar(page).getByRole('link', { name: /World Ledger/ }).click();
  await expect(page.getByRole('navigation', { name: 'Breadcrumb' })).toContainText('World Ledger');
  await page.getByRole('button', { name: 'Go back', exact: true }).click();
  await expect(page).toHaveURL(/\/manuscripts\/ms1$/);
  expect(world.writes).toHaveLength(0);
});
