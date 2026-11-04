# Labelling brief

Thank you for helping. This takes about 30–40 minutes and can be done in more than one sitting.

## What you are doing

You will see 50 pictures from video-game-like scenes. Under each picture is a short list of statements, such as
"a tree stump is visible" or "a person wearing a teal hooded cloak is visible". For each statement, answer:

- **Yes**: the picture clearly shows it.
- **No**: it clearly does not, or the picture shows something that contradicts it.
- **Can't tell**: too blurry, dark or small to decide.

Judge the thing, not the art style. A statement about a person's clothes is Yes only if a figure wearing that
colour and garment is there. Don't be generous: a vaguely similar object is No.

Please answer on your own, without discussing the pictures with anyone, and without looking at anyone else's
answers. There are no right answers to aim for; we want to know what a careful person sees.

## How to start

The page runs on this computer. In a terminal, in the `everfold` folder:

```
.venv/bin/python -m everfold.cli label --labels labels-v2-human2 --labeler human2
```

Then open http://127.0.0.1:8770 in a browser.

Keys: **1** Yes, **2** No, **3** Can't tell, **↑ ↓** move between statements, **Enter** save and go to the next
picture. Every picture is saved as soon as you finish it. To stop, close the browser tab and press Ctrl+C in the
terminal; run the same command again later to pick up where you left off.
