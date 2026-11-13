import { Component, type ReactNode } from 'react'

interface State {
  error: Error | null
}

/** Shows a friendly recovery screen instead of a blank page if something breaks while rendering. */
export class ErrorBoundary extends Component<{ children: ReactNode }, State> {
  state: State = { error: null }

  static getDerivedStateFromError(error: Error): State {
    return { error }
  }

  render() {
    if (!this.state.error) return this.props.children
    const stale = /dynamically imported module|Failed to fetch/i.test(this.state.error.message)
    return (
      <div className="flex min-h-screen items-center justify-center p-6">
        <div className="max-w-sm text-center">
          <h1 className="text-2xl font-bold">Something went wrong</h1>
          <p className="mt-2 text-sm text-muted">
            {stale ? 'A new version of CourtIQ is available.' : 'This page hit an unexpected error. Reloading usually fixes it.'}
          </p>
          <button className="mt-4 rounded-xl bg-court-800 px-4 py-2.5 text-sm font-semibold text-white" onClick={() => window.location.reload()}>
            Reload
          </button>
        </div>
      </div>
    )
  }
}
