import { defineComponent } from 'vue'
import { flushPromises, mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import KnowledgeSidePanels from './KnowledgeSidePanels.vue'

const nodeDetailStub = defineComponent({
  props: ['node'],
  emits: ['review-edge', 'set-overlay-planning'],
  template: `
    <section>
      <button data-testid="review-edge" @click="$emit('review-edge', 'edge-001', 'confirmed')">review</button>
      <button data-testid="set-overlay-planning" @click="$emit('set-overlay-planning', { id: 'node-001' }, true)">plan</button>
    </section>
  `,
})

const entityMetadataDrawerStub = defineComponent({
  props: ['modelValue', 'loading', 'metadata'],
  emits: ['update:modelValue'],
  template: '<button data-testid="entity-close" @click="$emit(\'update:modelValue\', false)">close</button>',
})

const knowledgeOverlayDrawerStub = defineComponent({
  props: ['visible', 'displayMode', 'overlayDraftMode', 'overlayCandidateFilter', 'promotionSecret'],
  emits: [
    'update:visible',
    'update:displayMode',
    'update:overlayDraftMode',
    'update:overlayCandidateFilter',
    'update:overlaySearchQuery',
    'update-overlay-form',
    'prepare-goal-draft',
    'search-overlay-results',
    'add-search-result-to-overlay',
    'preview-overlay-extraction-payload',
    'toggle-preview-candidate',
    'edit-node',
    'update-resource-binding',
    'update:promotionSecret',
    'bind-resource',
    'submit-overlay-draft',
  ],
  template: `
    <section>
      <button data-testid="drawer-visible" @click="$emit('update:visible', false)">visible</button>
      <button data-testid="display-mode" @click="$emit('update:displayMode', 'technical')">mode</button>
      <button data-testid="draft-mode" @click="$emit('update:overlayDraftMode', 'goal_draft')">draft</button>
      <button data-testid="candidate-filter" @click="$emit('update:overlayCandidateFilter', 'ready')">filter</button>
      <button data-testid="search-query" @click="$emit('update:overlaySearchQuery', '随机森林')">query</button>
      <button data-testid="overlay-form" @click="$emit('update-overlay-form', { sourceType: 'search_url' })">form</button>
      <button data-testid="prepare-draft" @click="$emit('prepare-goal-draft')">prepare</button>
      <button data-testid="search-overlay" @click="$emit('search-overlay-results')">search</button>
      <button data-testid="add-search" @click="$emit('add-search-result-to-overlay', { title: '随机森林入门', url: 'https://example.com/random-forest', snippet: '随机森林资料', score: 0.9 }, 0)">add</button>
      <button data-testid="preview-payload" @click="$emit('preview-overlay-extraction-payload')">preview</button>
      <button data-testid="toggle-candidate" @click="$emit('toggle-preview-candidate', 'nodes', 1, true)">toggle</button>
      <button data-testid="edit-node" @click="$emit('edit-node', { node_id: 'node-001' })">edit</button>
      <button data-testid="resource-binding" @click="$emit('update-resource-binding', 'targetId', 'node-001')">bind-field</button>
      <button data-testid="promotion-secret" @click="$emit('update:promotionSecret', 'secret-001')">secret</button>
      <button data-testid="bind-resource" @click="$emit('bind-resource')">bind</button>
      <button data-testid="submit-draft" @click="$emit('submit-overlay-draft')">submit</button>
    </section>
  `,
})

const candidateEditorDialogStub = defineComponent({
  props: ['visible', 'candidateEditor'],
  emits: ['update:visible', 'quick-fix', 'save'],
  template: `
    <section>
      <button data-testid="candidate-visible" @click="$emit('update:visible', false)">visible</button>
      <button data-testid="quick-fix" @click="$emit('quick-fix', 'missing_fields:name')">quick</button>
      <button data-testid="save-candidate" @click="$emit('save')">save</button>
    </section>
  `,
})

function mountPanels(overrides: Record<string, unknown> = {}) {
  return mount(KnowledgeSidePanels, {
    props: {
      selectedNode: {
        id: 'node-001',
        label: '线性回归',
        category: 'model',
        adjacent_edges: [],
        incoming_edges: [],
        outgoing_edges: [],
      } as any,
      entityDrawerVisible: true,
      entityLoading: false,
      entityMetadata: {} as any,
      overlayDrawerProps: { visible: true } as any,
      candidateEditorDialogProps: {
        visible: true,
        candidateEditor: { visible: true, errors: [], form: {} },
      } as any,
      ...overrides,
    },
    global: {
      stubs: {
        NodeDetail: nodeDetailStub,
        EntityMetadataDrawer: entityMetadataDrawerStub,
        KnowledgeOverlayDrawer: knowledgeOverlayDrawerStub,
        OverlayCandidateEditorDialog: candidateEditorDialogStub,
      },
    },
  })
}

async function click(wrapper: ReturnType<typeof mountPanels>, testId: string) {
  await wrapper.find(`[data-testid="${testId}"]`).trigger('click')
}

describe('KnowledgeSidePanels', () => {
  it('forwards node detail and entity drawer events', async () => {
    const wrapper = mountPanels()
    await flushPromises()

    await click(wrapper, 'review-edge')
    await click(wrapper, 'set-overlay-planning')
    await click(wrapper, 'entity-close')

    expect(wrapper.emitted('review-edge')).toEqual([['edge-001', 'confirmed']])
    expect(wrapper.emitted('set-overlay-planning')).toEqual([[{ id: 'node-001' }, true]])
    expect(wrapper.emitted('update:entityDrawerVisible')).toEqual([[false]])
  })

  it('forwards overlay drawer model and workflow events', async () => {
    const wrapper = mountPanels()
    await flushPromises()

    await click(wrapper, 'drawer-visible')
    await click(wrapper, 'display-mode')
    await click(wrapper, 'draft-mode')
    await click(wrapper, 'candidate-filter')
    await click(wrapper, 'search-query')
    await click(wrapper, 'overlay-form')
    await click(wrapper, 'prepare-draft')
    await click(wrapper, 'search-overlay')
    await click(wrapper, 'add-search')
    await click(wrapper, 'preview-payload')
    await click(wrapper, 'toggle-candidate')
    await click(wrapper, 'edit-node')
    await click(wrapper, 'resource-binding')
    await click(wrapper, 'promotion-secret')
    await click(wrapper, 'bind-resource')
    await click(wrapper, 'submit-draft')

    expect(wrapper.emitted('update-overlay-drawer-visible')).toEqual([[false]])
    expect(wrapper.emitted('update-display-mode')).toEqual([['technical']])
    expect(wrapper.emitted('update-overlay-draft-mode')).toEqual([['goal_draft']])
    expect(wrapper.emitted('update-overlay-candidate-filter')).toEqual([['ready']])
    expect(wrapper.emitted('update-overlay-search-query')).toEqual([['随机森林']])
    expect(wrapper.emitted('update-overlay-form')).toEqual([[{ sourceType: 'search_url' }]])
    expect(wrapper.emitted('prepare-goal-draft')).toHaveLength(1)
    expect(wrapper.emitted('search-overlay-results')).toHaveLength(1)
    expect(wrapper.emitted('add-search-result-to-overlay')).toEqual([[{ title: '随机森林入门', url: 'https://example.com/random-forest', snippet: '随机森林资料', score: 0.9 }, 0]])
    expect(wrapper.emitted('preview-overlay-extraction-payload')).toHaveLength(1)
    expect(wrapper.emitted('toggle-preview-candidate')).toEqual([['nodes', 1, true]])
    expect(wrapper.emitted('edit-node')).toEqual([[{ node_id: 'node-001' }]])
    expect(wrapper.emitted('update-resource-binding')).toEqual([['targetId', 'node-001']])
    expect(wrapper.emitted('update-promotion-secret')).toEqual([['secret-001']])
    expect(wrapper.emitted('bind-resource')).toHaveLength(1)
    expect(wrapper.emitted('submit-overlay-draft')).toHaveLength(1)
  })

  it('forwards candidate editor dialog events', async () => {
    const wrapper = mountPanels()
    await flushPromises()

    await click(wrapper, 'candidate-visible')
    await click(wrapper, 'quick-fix')
    await click(wrapper, 'save-candidate')

    expect(wrapper.emitted('update-candidate-editor-visible')).toEqual([[false]])
    expect(wrapper.emitted('quick-fix')).toEqual([['missing_fields:name']])
    expect(wrapper.emitted('save-candidate-editor')).toHaveLength(1)
  })
})
