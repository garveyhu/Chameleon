import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { Suspense } from 'react';
import { RouterProvider } from 'react-router-dom';
import { Toaster } from 'sonner';

import { Spinner } from '@/core/components/common/spinner';
import { TooltipProvider } from '@/core/components/ui/tooltip';
import '@/core/i18n';
import { router } from '@/router';

import '@/assets/styles/index.css';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30 * 1000,
      refetchOnWindowFocus: false,
      retry: 1,
    },
  },
});

const FullscreenLoading = () => (
  <div className="flex h-screen items-center justify-center bg-[var(--color-warm)]">
    <div className="flex flex-col items-center gap-4">
      <Spinner size="lg" />
      <span className="text-sm text-stone-500">加载中...</span>
    </div>
  </div>
);

const App = () => (
  <QueryClientProvider client={queryClient}>
    <TooltipProvider delayDuration={250} skipDelayDuration={100}>
      <Suspense fallback={<FullscreenLoading />}>
        <RouterProvider router={router} />
      </Suspense>
      <Toaster
        position="top-right"
        offset={{ top: 64, right: 16 }}
        closeButton
        toastOptions={{
          classNames: {
            toast:
              '!bg-white !border !border-stone-200 !shadow-[0_8px_24px_-8px_rgba(0,0,0,0.12)] !text-stone-900 !font-medium',
            title: '!text-stone-900 !font-medium !text-[12.5px]',
            description: '!text-stone-500 !text-[11.5px]',
            success: '[&_[data-icon]]:!text-emerald-600',
            error: '[&_[data-icon]]:!text-rose-600',
            warning: '[&_[data-icon]]:!text-amber-600',
            info: '[&_[data-icon]]:!text-sky-600',
            closeButton:
              '!bg-white !text-stone-400 hover:!text-stone-800 !border-stone-200',
          },
        }}
      />
    </TooltipProvider>
  </QueryClientProvider>
);

export default App;
