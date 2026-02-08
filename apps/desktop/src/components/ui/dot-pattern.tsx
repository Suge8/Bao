import type { SVGProps } from "react";
import { cn } from "@/lib/utils";

type DotPatternProps = SVGProps<SVGSVGElement> & {
  width?: number;
  height?: number;
  cx?: number;
  cy?: number;
  cr?: number;
};

export function DotPattern({
  className,
  width = 24,
  height = 24,
  cx = 1,
  cy = 1,
  cr = 1,
  ...props
}: DotPatternProps) {
  const id = "bao-dot-pattern";
  return (
    <svg
      aria-hidden
      className={cn("absolute inset-0 h-full w-full", className)}
      {...props}
    >
      <title>Dot pattern background</title>
      <defs>
        <pattern id={id} width={width} height={height} patternUnits="userSpaceOnUse">
          <circle cx={cx} cy={cy} r={cr} fill="currentColor" />
        </pattern>
      </defs>
      <rect width="100%" height="100%" fill={`url(#${id})`} />
    </svg>
  );
}
