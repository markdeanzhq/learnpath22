import { computed, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  buildGraphQuery,
  normalizeGraphPathId,
  normalizeGraphScope,
  type GraphScope,
} from '@/api/modules/graph'

export function useGraphRouteSync() {
  const route = useRoute()
  const router = useRouter()
  const scope = ref<GraphScope>(normalizeGraphScope(route.query.scope))
  const requestedScope = computed<GraphScope>(() => normalizeGraphScope(route.query.scope))
  const requestedPathId = computed<string | undefined>(() => normalizeGraphPathId(requestedScope.value, route.query.path_id))
  const requestedNodeId = computed<string | null>(() => normalizeRouteNodeId(route.query.nodeId))
  const requestedSessionId = computed<string | null>(() => normalizeRouteSessionId(route.query.sessionId))
  const goalDraftResolutionSessionId = computed<string | null>(() => (
    normalizeGoalDraftFlag(route.query.goalDraft) ? normalizeRouteSessionId(route.query.resolutionSessionId) : null
  ))
  const graphQuery = computed(() => buildGraphQuery({
    scope: scope.value,
    path_id: requestedPathId.value,
    nodeId: requestedNodeId.value || undefined,
  }))

  function graphRouteQuery(nextScope: GraphScope, nodeId?: string | null, sessionId?: string | null) {
    return {
      ...buildGraphQuery({
        scope: nextScope,
        path_id: nextScope === 'path' ? requestedPathId.value : undefined,
        nodeId: nodeId || undefined,
      }),
      ...(sessionId ? { sessionId } : {}),
    }
  }

  async function replaceGraphRoute(
    nextScope: GraphScope,
    nodeId?: string | null,
    sessionId: string | null = requestedSessionId.value,
  ) {
    await router.replace({
      name: 'Knowledge',
      query: Object.fromEntries(
        Object.entries(graphRouteQuery(nextScope, nodeId, sessionId)).filter((entry): entry is [string, string] => typeof entry[1] === 'string'),
      ),
    })
  }

  return {
    scope,
    requestedScope,
    requestedPathId,
    requestedNodeId,
    requestedSessionId,
    goalDraftResolutionSessionId,
    graphQuery,
    replaceGraphRoute,
  }
}

function firstQueryValue(value: unknown): unknown {
  return Array.isArray(value) ? value[0] : value
}

function normalizeRouteSessionId(value: unknown): string | null {
  const nextValue = firstQueryValue(value)
  return typeof nextValue === 'string' && nextValue.trim() ? nextValue.trim() : null
}

function normalizeRouteNodeId(value: unknown): string | null {
  const nextValue = firstQueryValue(value)
  return typeof nextValue === 'string' && nextValue.trim() ? nextValue.trim() : null
}

function normalizeGoalDraftFlag(value: unknown): boolean {
  const nextValue = firstQueryValue(value)
  return nextValue === '1' || nextValue === 'true'
}
