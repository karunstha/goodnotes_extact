import unittest

from PIL import Image, ImageDraw

from goodnotes_ocr.checkboxes import find_checkboxes

BLUE, RED = (0, 122, 255), (255, 2, 2)


def page(boxes, ticked=(), extra=None):
    """A white page with square outlines at the given (x, y, size) and red ticks in some."""
    img = Image.new("RGB", (1200, 1600), "white")
    d = ImageDraw.Draw(img)
    for i, (x, y, size) in enumerate(boxes):
        d.rectangle((x, y, x + size, y + size), outline=BLUE, width=8)
        if i in ticked:
            d.line([(x + 0.2 * size, y + 0.5 * size), (x + 0.4 * size, y + 0.8 * size),
                    (x + 1.2 * size, y - 0.2 * size)], fill=RED, width=10)
    if extra:
        extra(d)
    return img


class FindCheckboxesTests(unittest.TestCase):
    def test_boxes_are_numbered_top_to_bottom(self):
        boxes = find_checkboxes(page([(200, 900, 110), (205, 300, 120), (198, 600, 100)]))
        self.assertEqual([b.n for b in boxes], [1, 2, 3])
        self.assertEqual([b.y0 // 100 for b in boxes], [3, 6, 9])
        self.assertFalse(any(b.ticked for b in boxes))

    def test_red_ink_inside_marks_a_box_ticked(self):
        boxes = find_checkboxes(page([(200, 300, 120), (200, 600, 120), (200, 900, 120)], ticked={1}))
        self.assertEqual([b.ticked for b in boxes], [False, True, False])

    def test_a_tick_crossing_the_outline_does_not_hide_the_box(self):
        boxes = find_checkboxes(page([(200, 300, 120), (200, 600, 120)], ticked={0, 1}))
        self.assertEqual(len(boxes), 2)

    def test_round_letters_are_not_boxes(self):
        def letters(d):
            d.ellipse((210, 100, 300, 220), outline=BLUE, width=8)   # an "O" above the boxes
            d.ellipse((500, 320, 580, 420), outline=BLUE, width=8)   # an "o" in a task line
        boxes = find_checkboxes(page([(200, 300, 120), (200, 600, 120)], extra=letters))
        self.assertEqual([b.y0 // 100 for b in boxes], [3, 6])

    def test_template_dots_and_blank_pages_give_nothing(self):
        def dots(d):
            for x in range(50, 1200, 100):
                for y in range(50, 1600, 100):
                    d.ellipse((x, y, x + 6, y + 6), fill=(205, 205, 205))
        self.assertEqual(find_checkboxes(page([], extra=dots)), [])


if __name__ == "__main__":
    unittest.main()
