import { motion, type MotionProps } from "motion/react";

const itemAnimations: MotionProps = {
  initial: { scale: 0, opacity: 0 },
  animate: { scale: 1, opacity: 1, originY: 0 },
  exit: { scale: 0, opacity: 0 },
  transition: { type: "spring", stiffness: 350, damping: 40 },
};

export function AnimatedListItem({ children }: { children: React.ReactNode }) {
  return (
    <motion.div {...itemAnimations} layout className="mx-auto w-full">
      {children}
    </motion.div>
  );
}
