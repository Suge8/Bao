import { fireEvent, render, screen } from "@testing-library/react";
import { Dialog } from "./dialog";

test("Dialog closes on overlay click", () => {
  const onOpenChange = vi.fn();
  render(
    <Dialog open={true} onOpenChange={onOpenChange} title="T">
      Body
    </Dialog>,
  );
  fireEvent.click(screen.getByRole("button", { name: "Close dialog" }));
  expect(onOpenChange).toHaveBeenCalledWith(false);
});
