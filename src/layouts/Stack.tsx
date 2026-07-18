import { HTMLAttributes, ReactNode } from 'react';

export interface StackProps extends HTMLAttributes<HTMLDivElement> {
  direction?: 'row' | 'col';
  align?: 'start' | 'center' | 'end' | 'baseline' | 'stretch';
  justify?: 'start' | 'center' | 'end' | 'between' | 'around' | 'evenly';
  children?: ReactNode;
}

export function Stack({
  direction = 'col',
  align,
  justify,
  children,
  className = '',
  style,
  ...props
}: StackProps) {
  const flexClasses = [
    'flex',
    direction === 'col' ? 'flex-col' : 'flex-row',
    align ? `items-${align}` : '',
    justify ? `justify-${justify}` : '',
    className
  ].filter(Boolean).join(' ');

  return (
    <div className={flexClasses} style={style} {...props}>
      {children}
    </div>
  );
}
