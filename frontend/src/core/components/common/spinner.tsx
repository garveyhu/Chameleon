import { Loader2 } from 'lucide-react';

import { cn } from '@/core/lib/cn';

interface SpinnerProps {
  size?: 'sm' | 'md' | 'lg';
  className?: string;
}

const sizeMap = {
  sm: 'h-4 w-4',
  md: 'h-6 w-6',
  lg: 'h-8 w-8',
};

export const Spinner = ({ size = 'md', className }: SpinnerProps) => (
  <Loader2 className={cn('animate-spin text-primary-600', sizeMap[size], className)} />
);
