// Promise-based styled confirmation. ConfirmDialog renders the active request
// from the default layout; any component can await confirm() in place of the
// unstyled window.confirm.

export interface ConfirmOptions {
  title: string
  message: string
  confirmLabel?: string
  cancelLabel?: string
  tone?: 'primary' | 'danger'
}

interface ConfirmRequest extends ConfirmOptions {
  resolve: (value: boolean) => void
}

export function useConfirm() {
  const request = useState<ConfirmRequest | null>('ui.confirm-request', () => null)

  async function confirm(options: ConfirmOptions): Promise<boolean> {
    if (request.value) request.value.resolve(false)
    return await new Promise<boolean>((resolve) => {
      request.value = { ...options, resolve }
    })
  }

  function settle(value: boolean): void {
    request.value?.resolve(value)
    request.value = null
  }

  return { request, confirm, settle }
}
