import { forwardRef, type ButtonHTMLAttributes, type ReactNode } from "react";
import { motion, type MotionProps } from "motion/react";
import { cn } from "@/lib/utils";

const animationProps: MotionProps = {
  initial: { "--x": "100%", scale: 0.98 },
  animate: { "--x": "-100%", scale: 1 },
  whileTap: { scale: 0.96 },
  transition: {
    repeat: Infinity,
    repeatType: "loop",
    repeatDelay: 1.2,
    type: "spring",
    stiffness: 24,
    damping: 16,
    mass: 2,
    scale: {
      type: "spring",
      stiffness: 220,
      damping: 10,
      mass: 0.5,
    },
  },
};

type ShinyButtonProps = Omit<ButtonHTMLAttributes<HTMLButtonElement>, keyof MotionProps> &
  MotionProps & {
    children: ReactNode;
  };

export const ShinyButton = forwardRef<HTMLButtonElement, ShinyButtonProps>(
  ({ children, className, disabled, ...props }, ref) => {
    return (
      <motion.button
        ref={ref}
        disabled={disabled}
        className={cn(
          "relative inline-flex items-center justify-center rounded-xl border px-3 py-2 text-sm font-medium transition-shadow duration-300",
          "bg-background/80 backdrop-blur-xl hover:shadow-md",
          "disabled:cursor-not-allowed disabled:opacity-55",
          className,
        )}
        {...animationProps}
        {...props}
      >
        <span
          className="relative block whitespace-nowrap"
          style={{
            maskImage:
              "linear-gradient(-75deg, rgba(0,0,0,0.9) calc(var(--x) + 20%), transparent calc(var(--x) + 30%), rgba(0,0,0,0.9) calc(var(--x) + 100%))",
          }}
        >
          {children}
        </span>
        <span
          className="pointer-events-none absolute inset-0 rounded-[inherit] p-px"
          style={{
            mask: "linear-gradient(rgb(0,0,0), rgb(0,0,0)) content-box exclude, linear-gradient(rgb(0,0,0), rgb(0,0,0))",
            WebkitMask:
              "linear-gradient(rgb(0,0,0), rgb(0,0,0)) content-box exclude, linear-gradient(rgb(0,0,0), rgb(0,0,0))",
            backgroundImage:
              "linear-gradient(-75deg, rgba(20,184,166,0.1) calc(var(--x)+20%), rgba(34,211,238,0.45) calc(var(--x)+25%), rgba(20,184,166,0.1) calc(var(--x)+100%))",
          }}
        />
      </motion.button>
    );
  },
);

ShinyButton.displayName = "ShinyButton";
