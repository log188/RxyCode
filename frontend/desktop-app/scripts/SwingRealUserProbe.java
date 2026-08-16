import java.awt.Component;
import java.awt.Container;
import java.awt.Rectangle;
import java.awt.Window;
import java.awt.image.BufferedImage;
import java.io.File;
import java.lang.reflect.Method;
import java.util.ArrayList;
import java.util.List;
import javax.imageio.ImageIO;
import javax.swing.AbstractButton;
import javax.swing.JDialog;
import javax.swing.JFrame;
import javax.swing.JTextArea;
import javax.swing.JTextField;
import javax.swing.SwingUtilities;
import javax.swing.Timer;

/**
 * Drives a visible Swing number-bomb window like a person: invalid input,
 * a real guess, new-game, then close. Captures the JFrame pixels after each step.
 */
public final class SwingRealUserProbe {
  private static volatile boolean dismissDialogs = true;

  public static void main(String[] args) throws Exception {
    if (args.length < 2) {
      System.err.println("usage: SwingRealUserProbe <mainClass> <screenshotDir>");
      System.exit(2);
    }
    String mainClass = args[0];
    File outDir = new File(args[1]);
    outDir.mkdirs();
    startDialogDismisser();
    Method main = Class.forName(mainClass).getMethod("main", String[].class);
    SwingUtilities.invokeLater(() -> {
      try {
        main.invoke(null, (Object) new String[0]);
      } catch (Exception e) {
        e.printStackTrace();
        System.exit(1);
      }
    });
    JFrame frame = waitForFrame(12_000);
    if (frame == null) {
      System.out.println("{\"ok\":false,\"reason\":\"no JFrame appeared\"}");
      System.exit(1);
    }
    Thread.sleep(700);
    shot(frame, new File(outDir, "01-open.png"));
    JTextField field = findField(frame);
    AbstractButton guess = findButton(frame, "猜测", "提交");
    AbstractButton neu = findButton(frame, "新游戏");
    if (field == null || guess == null) {
      System.out.println("{\"ok\":false,\"reason\":\"missing field or guess button\"}");
      frame.dispose();
      System.exit(1);
    }
    setText(field, "abc");
    click(guess);
    Thread.sleep(600);
    shot(frame, new File(outDir, "02-invalid-letter.png"));
    setText(field, "12.5");
    click(guess);
    Thread.sleep(600);
    shot(frame, new File(outDir, "03-invalid-decimal.png"));
    setText(field, "1");
    click(guess);
    Thread.sleep(700);
    shot(frame, new File(outDir, "04-after-guess.png"));
    String rangeAfter = frame.getTitle() + " " + collectText(frame);
    if (neu != null) {
      click(neu);
      Thread.sleep(500);
      shot(frame, new File(outDir, "05-new-game.png"));
    }
    frame.dispose();
    boolean narrowed = rangeAfter.contains("范围") || rangeAfter.matches("(?s).*\\d+.*");
    System.out.println("{\"ok\":true,\"narrowedOrVisible\":" + narrowed + ",\"title\":\"" + escape(frame.getTitle()) + "\"}");
    System.exit(0);
  }

  private static void startDialogDismisser() {
    Timer timer = new Timer(180, e -> {
      if (!dismissDialogs) return;
      for (Window window : Window.getWindows()) {
        if (window instanceof JDialog && window.isShowing()) {
          AbstractButton ok = findButton(window, "确定", "OK", "是");
          if (ok != null) ok.doClick();
          else window.dispose();
        }
      }
    });
    timer.setRepeats(true);
    timer.start();
  }

  private static JFrame waitForFrame(int timeoutMs) throws Exception {
    long deadline = System.currentTimeMillis() + timeoutMs;
    while (System.currentTimeMillis() < deadline) {
      for (Window window : Window.getWindows()) {
        if (window instanceof JFrame && window.isShowing()) return (JFrame) window;
      }
      Thread.sleep(100);
    }
    return null;
  }

  private static void setText(JTextField field, String text) throws Exception {
    SwingUtilities.invokeAndWait(() -> {
      field.setText(text);
      field.requestFocusInWindow();
    });
  }

  private static void click(AbstractButton button) throws Exception {
    SwingUtilities.invokeAndWait(button::doClick);
  }

  private static void shot(JFrame frame, File file) throws Exception {
    SwingUtilities.invokeAndWait(() -> {
      try {
        Rectangle bounds = frame.getBounds();
        BufferedImage image = new BufferedImage(Math.max(1, bounds.width), Math.max(1, bounds.height), BufferedImage.TYPE_INT_RGB);
        frame.paint(image.getGraphics());
        ImageIO.write(image, "png", file);
      } catch (Exception e) {
        throw new RuntimeException(e);
      }
    });
  }

  private static JTextField findField(Container root) {
    for (Component c : walk(root)) {
      if (c instanceof JTextField) return (JTextField) c;
    }
    return null;
  }

  private static AbstractButton findButton(Container root, String... needles) {
    for (Component c : walk(root)) {
      if (!(c instanceof AbstractButton)) continue;
      String text = String.valueOf(((AbstractButton) c).getText());
      for (String needle : needles) {
        if (text.contains(needle)) return (AbstractButton) c;
      }
    }
    return null;
  }

  private static String collectText(Container root) {
    StringBuilder out = new StringBuilder();
    for (Component c : walk(root)) {
      if (c instanceof javax.swing.JLabel) out.append(((javax.swing.JLabel) c).getText()).append(' ');
      if (c instanceof JTextArea) out.append(((JTextArea) c).getText()).append(' ');
    }
    return out.toString();
  }

  private static List<Component> walk(Container root) {
    List<Component> all = new ArrayList<>();
    walk(root, all);
    return all;
  }

  private static void walk(Container root, List<Component> all) {
    for (Component child : root.getComponents()) {
      all.add(child);
      if (child instanceof Container) walk((Container) child, all);
    }
  }

  private static String escape(String value) {
    return value == null ? "" : value.replace("\\", "\\\\").replace("\"", "\\\"");
  }
}
