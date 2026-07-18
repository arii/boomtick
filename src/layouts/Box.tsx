import { HTMLAttributes, ReactNode } from 'react';

export interface BoxProps extends HTMLAttributes<HTMLDivElement> {
  children?: ReactNode;
}

export function Box({ children, ...props }: BoxProps) {
  return <div {...props}>{children}</div>;
}
