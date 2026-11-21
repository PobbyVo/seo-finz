'use client';

import React, { useId } from 'react';

export function ResponsiveTable({
  caption,
  children,
}: {
  caption: string;
  children: React.ReactNode;
}) {
  const captionId = useId();
  return (
    <div tabIndex={0} role="region" aria-labelledby={captionId} className="table-wrapper">
      <table className="finz-table">
        <caption id={captionId} className="visually-hidden">
          {caption}
        </caption>
        {children}
      </table>
    </div>
  );
}
