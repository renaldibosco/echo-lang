package echo;

import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.io.OutputStream;
import java.lang.reflect.Method;
import java.lang.reflect.Modifier;
import java.math.BigDecimal;
import java.math.MathContext;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.text.SimpleDateFormat;
import java.util.*;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * Runtime for Java code made from Echo (echolang java FILE.echo).
 * Values: Long, Double, String, Boolean, null (nothing), ArrayList (list), LinkedHashMap (map), EchoFn (function).
 * Drop this file in src/main/java/echo/ of an Android project, or compile it next to the converted program.
 */
public final class EchoRuntime {
    private EchoRuntime() {}

    // ------------------------------------------------------------------ basics
    public interface EchoFn { Object call(Object... args); }

    /** A function value that remembers its name (used for printing and truth tables). */
    public static final class NamedFn implements EchoFn {
        public final String name; final EchoFn f;
        public NamedFn(String name, EchoFn f) { this.name = name; this.f = f; }
        public Object call(Object... args) { return f.call(args); }
        public String toString() { return "<function " + name + ">"; }
    }

    public static EchoFn named(String name, EchoFn f) { return new NamedFn(name, f); }

    /** An Echo error. `code` is the Echo error code (E101-E502); run `echolang explain CODE` to read about it. */
    public static class EchoError extends RuntimeException {
        public final String code;
        public EchoError(String m) { this("E404", m); }
        public EchoError(String code, String m) { super(m); this.code = code; }
        @Override public String toString() { return "Error " + code + ": " + getMessage(); }
    }

    /** A named value passed to a built-in, like translate(seq, to_stop: true). */
    public static final class Kw {
        public final String name; public final Object value;
        Kw(String n, Object v) { name = n; value = v; }
    }

    public static Kw kw(String name, Object value) { return new Kw(name, value); }

    /** Where say() writes. Android apps can replace it, e.g. to append to a TextView. */
    public interface Output { void line(String text); }
    private static final java.io.PrintStream UTF8_OUT = utf8Out();
    private static java.io.PrintStream utf8Out() {
        try { return new java.io.PrintStream(new java.io.FileOutputStream(java.io.FileDescriptor.out), true, "UTF-8"); }
        catch (java.io.UnsupportedEncodingException e) { return System.out; }
    }
    public static Output out = text -> UTF8_OUT.println(text);
    /** Where ask() reads from. */
    public interface Input { String read(String prompt); }
    public static Input in = prompt -> {
        System.out.print(prompt);
        try { return new BufferedReader(new InputStreamReader(System.in)).readLine(); }
        catch (Exception e) { return ""; }
    };

    private static final Random RNG = new Random();

    static Object arg(Object[] a, int i, String name, Object def) {
        for (Object o : a) if (o instanceof Kw && ((Kw) o).name.equals(name)) return ((Kw) o).value;
        int pos = 0;
        for (Object o : a) {
            if (o instanceof Kw) continue;
            if (pos == i) return o;
            pos++;
        }
        return def;
    }

    static Object req(Object[] a, int i, String name, String fn) {
        Object v = arg(a, i, name, MISSING);
        if (v == MISSING) throw new EchoError(fn + "() is missing the value for '" + name + "'.");
        return v;
    }

    private static final Object MISSING = new Object();

    public static Object arg(Object[] a, int i) { return i < a.length ? a[i] : null; }

    // ------------------------------------------------------------------ show / types
    public static String show(Object v) { return show(v, false); }

    static String show(Object v, boolean nested) {
        if (v == null) return "nothing";
        if (v instanceof Boolean) return ((Boolean) v) ? "true" : "false";
        if (v instanceof Long || v instanceof Integer) return v.toString();
        if (v instanceof Double) return fmt((Double) v);
        if (v instanceof String) {
            if (!nested) return (String) v;
            return "\"" + ((String) v).replace("\\", "\\\\").replace("\"", "\\\"").replace("\n", "\\n") + "\"";
        }
        if (v instanceof List) {
            StringBuilder b = new StringBuilder("[");
            List<?> l = (List<?>) v;
            for (int i = 0; i < l.size(); i++) { if (i > 0) b.append(", "); b.append(show(l.get(i), true)); }
            return b.append("]").toString();
        }
        if (v instanceof Map) {
            Map<?, ?> m = (Map<?, ?>) v;
            StringBuilder b = new StringBuilder();
            Object t = m.get("_type");
            boolean first = true;
            for (Map.Entry<?, ?> e : m.entrySet()) {
                if ("_type".equals(e.getKey())) continue;
                if (!first) b.append(", ");
                first = false;
                b.append(e.getKey() instanceof String ? (String) e.getKey() : show(e.getKey(), true))
                 .append(": ").append(show(e.getValue(), true));
            }
            return t != null ? t + "(" + b + ")" : "{" + b + "}";
        }
        if (v instanceof EchoFn) return v instanceof NamedFn ? v.toString() : "<function>";
        return String.valueOf(v);
    }

    static String fmt(double d) {
        if (Double.isNaN(d)) return "not a number";
        if (Double.isInfinite(d)) return d > 0 ? "infinity" : "-infinity";
        if (d == Math.rint(d) && Math.abs(d) < 1e15) return Long.toString((long) d);
        BigDecimal bd = new BigDecimal(d).round(new MathContext(10));
        int exp = bd.precision() - bd.scale() - 1;
        if (exp < -4 || exp >= 10) {
            String s = String.format(Locale.ROOT, "%.9e", d);
            String[] p = s.split("e");
            String mant = p[0].contains(".") ? p[0].replaceAll("0+$", "").replaceAll("\\.$", "") : p[0];
            int ex = Integer.parseInt(p[1]);
            return mant + "e" + (ex < 0 ? "-" : "+") + String.format(Locale.ROOT, "%02d", Math.abs(ex));
        }
        return bd.stripTrailingZeros().toPlainString();
    }

    public static String type(Object v) {
        if (v == null) return "nothing";
        if (v instanceof Boolean) return "boolean";
        if (v instanceof Number) return "number";
        if (v instanceof String) return "text";
        if (v instanceof List) return "list";
        if (v instanceof Map) { Object t = ((Map<?, ?>) v).get("_type"); return t instanceof String ? (String) t : "map"; }
        if (v instanceof EchoFn) return "function";
        return v.getClass().getSimpleName();
    }

    public static boolean truthy(Object v) {
        if (v == null) return false;
        if (v instanceof Boolean) return (Boolean) v;
        if (v instanceof Number) return ((Number) v).doubleValue() != 0;
        if (v instanceof String) return !((String) v).isEmpty();
        if (v instanceof Collection) return !((Collection<?>) v).isEmpty();
        if (v instanceof Map) return !((Map<?, ?>) v).isEmpty();
        return true;
    }

    static boolean isNum(Object v) { return v instanceof Long || v instanceof Double || v instanceof Integer; }
    static boolean isInt(Object v) { return v instanceof Long || v instanceof Integer; }

    public static double toDouble(Object v) {
        if (isNum(v)) return ((Number) v).doubleValue();
        throw new EchoError("Expected a number, not " + type(v) + ".");
    }

    public static long toLong(Object v) {
        if (isInt(v)) return ((Number) v).longValue();
        if (v instanceof Double) return (long) (double) (Double) v;
        throw new EchoError("Expected a whole number, not " + type(v) + ".");
    }

    static Object num(double d) { return d; }

    static Object clean(double d) { return d; }

    // ------------------------------------------------------------------ building values
    public static String str(Object... parts) {
        StringBuilder b = new StringBuilder();
        for (Object p : parts) b.append(show(p));
        return b.toString();
    }

    public static ArrayList<Object> list(Object... items) { return new ArrayList<>(Arrays.asList(items)); }

    public static LinkedHashMap<Object, Object> mapOf(Object... kv) {
        LinkedHashMap<Object, Object> m = new LinkedHashMap<>();
        for (int i = 0; i + 1 < kv.length; i += 2) m.put(kv[i], kv[i + 1]);
        return m;
    }

    public static void discard(Object v) {}

    // ------------------------------------------------------------------ operators
    public static Object add(Object a, Object b) {
        if (isInt(a) && isInt(b)) {
            long x = ((Number) a).longValue(), y = ((Number) b).longValue();
            long r = x + y;
            if (((x ^ r) & (y ^ r)) < 0) return (double) x + (double) y;
            return r;
        }
        if (isNum(a) && isNum(b)) return toDouble(a) + toDouble(b);
        if (a instanceof String || b instanceof String) return show(a) + show(b);
        if (a instanceof List && b instanceof List) {
            ArrayList<Object> r = new ArrayList<>((List<?>) a); r.addAll((List<?>) b); return r;
        }
        if (a instanceof Map && b instanceof Map) {
            LinkedHashMap<Object, Object> r = new LinkedHashMap<>((Map<?, ?>) a); r.putAll((Map<?, ?>) b); return r;
        }
        throw new EchoError("Can't add " + type(a) + " and " + type(b) + ".");
    }

    static void needNums(String op, Object a, Object b) {
        if (!isNum(a) || !isNum(b))
            throw new EchoError("'" + op + "' needs two numbers, not " + type(a) + " and " + type(b) + ".");
    }

    public static Object sub(Object a, Object b) {
        needNums("-", a, b);
        if (isInt(a) && isInt(b)) return ((Number) a).longValue() - ((Number) b).longValue();
        return toDouble(a) - toDouble(b);
    }

    public static Object mul(Object a, Object b) {
        if (a instanceof String && isInt(b)) return repeat((String) a, toLong(b));
        if (b instanceof String && isInt(a)) return repeat((String) b, toLong(a));
        if (a instanceof List && isInt(b)) {
            ArrayList<Object> r = new ArrayList<>();
            for (long i = 0; i < toLong(b); i++) r.addAll((List<?>) a);
            return r;
        }
        needNums("*", a, b);
        if (isInt(a) && isInt(b)) return ((Number) a).longValue() * ((Number) b).longValue();
        return toDouble(a) * toDouble(b);
    }

    static String repeat(String s, long n) {
        StringBuilder b = new StringBuilder();
        for (long i = 0; i < n; i++) b.append(s);
        return b.toString();
    }

    public static Object div(Object a, Object b) {
        needNums("/", a, b);
        if (toDouble(b) == 0) throw new EchoError("E401", "Division by zero.");
        if (isInt(a) && isInt(b) && ((Number) a).longValue() % ((Number) b).longValue() == 0)
            return ((Number) a).longValue() / ((Number) b).longValue();
        return toDouble(a) / toDouble(b);
    }

    public static Object floordiv(Object a, Object b) {
        needNums("//", a, b);
        if (toDouble(b) == 0) throw new EchoError("E401", "Division by zero.");
        if (isInt(a) && isInt(b)) return Math.floorDiv(((Number) a).longValue(), ((Number) b).longValue());
        return Math.floor(toDouble(a) / toDouble(b));
    }

    public static Object mod(Object a, Object b) {
        needNums("%", a, b);
        if (toDouble(b) == 0) throw new EchoError("E401", "Division by zero.");
        if (isInt(a) && isInt(b)) return Math.floorMod(((Number) a).longValue(), ((Number) b).longValue());
        double x = toDouble(a), y = toDouble(b);
        return x - y * Math.floor(x / y);
    }

    public static Object pow(Object a, Object b) {
        needNums("^", a, b);
        if (isInt(a) && isInt(b) && toLong(b) >= 0) {
            double d = Math.pow(toDouble(a), toDouble(b));
            if (Math.abs(d) < 9e15) return (long) d;
            return d;
        }
        return Math.pow(toDouble(a), toDouble(b));
    }

    public static Object neg(Object a) {
        if (isInt(a)) return -((Number) a).longValue();
        if (a instanceof Double) return -(Double) a;
        throw new EchoError("Can't make " + type(a) + " negative.");
    }

    public static boolean eq(Object a, Object b) {
        if (a == null || b == null) return a == b;
        if (a instanceof Boolean || b instanceof Boolean) return a.equals(b);
        if (isNum(a) && isNum(b)) return toDouble(a) == toDouble(b);
        return a.equals(b);
    }

    public static boolean ne(Object a, Object b) { return !eq(a, b); }

    static int cmp(Object a, Object b) {
        if (isNum(a) && isNum(b)) return Double.compare(toDouble(a), toDouble(b));
        if (a instanceof String && b instanceof String) return ((String) a).compareTo((String) b);
        throw new EchoError("Can't compare " + type(a) + " with " + type(b) + ".");
    }

    public static boolean lt(Object a, Object b) { return cmp(a, b) < 0; }
    public static boolean gt(Object a, Object b) { return cmp(a, b) > 0; }
    public static boolean le(Object a, Object b) { return cmp(a, b) <= 0; }
    public static boolean ge(Object a, Object b) { return cmp(a, b) >= 0; }

    public static boolean in(Object a, Object b) {
        if (b instanceof String) {
            if (!(a instanceof String)) throw new EchoError("To look inside text, the left side must be text.");
            return ((String) b).contains((String) a);
        }
        if (b instanceof List) { for (Object o : (List<?>) b) if (eq(o, a)) return true; return false; }
        if (b instanceof Map) return ((Map<?, ?>) b).containsKey(a) && !"_type".equals(a);
        throw new EchoError("E301", "Can't look inside " + type(b) + ".");
    }

    static boolean isSeq(String s) { return !s.isEmpty() && s.matches("[ACGTUNacgtun]+"); }

    static boolean bit(Object v) { return isInt(v) && (((Number) v).longValue() == 0 || ((Number) v).longValue() == 1); }

    static Object gateResult(Object a, Object b, boolean r) { return bit(a) && bit(b) ? (Object) (r ? 1L : 0L) : (Object) r; }

    /** Gates need both sides true/false, or both bits (0 or 1). */
    static void gateArgs(String op, Object a, Object b) {
        if ((a instanceof Boolean && b instanceof Boolean) || (bit(a) && bit(b))) return;
        Object bad = (a instanceof Boolean || bit(a)) ? b : a;
        if (!(a instanceof Boolean || bit(a)) || !(b instanceof Boolean || bit(b)))
            throw new EchoError("E301", "'" + op + "' needs true/false or bits (0 or 1), not " + describe(bad) + ".");
        throw new EchoError("E301", "'" + op + "' needs both sides to be true/false, or both to be bits (0 or 1); got "
                + describe(a) + " and " + describe(b) + ".");
    }
    static boolean on(Object v) { return v instanceof Boolean ? (Boolean) v : ((Number) v).longValue() == 1; }

    public static Object and(Object a, Object b) { gateArgs("and", a, b); return gateResult(a, b, on(a) && on(b)); }
    public static Object or(Object a, Object b) { gateArgs("or", a, b); return gateResult(a, b, on(a) || on(b)); }
    public static Object xor(Object a, Object b) { gateArgs("xor", a, b); return gateResult(a, b, on(a) != on(b)); }
    public static Object nand(Object a, Object b) { gateArgs("nand", a, b); return gateResult(a, b, !(on(a) && on(b))); }
    public static Object nor(Object a, Object b) { gateArgs("nor", a, b); return gateResult(a, b, !(on(a) || on(b))); }
    public static Object xnor(Object a, Object b) { gateArgs("xnor", a, b); return gateResult(a, b, on(a) == on(b)); }
    public static Object not(Object a) {
        if (a instanceof Boolean) return !(Boolean) a;
        if (bit(a)) return 1L - ((Number) a).longValue();
        throw new EchoError("E301", "'not' needs true/false or a bit (0 or 1), not " + describe(a) + ".");
    }

    /** if / else if / while: the condition must be a real boolean. */
    public static boolean cond(Object v, String word) {
        if (v instanceof Boolean) return (Boolean) v;
        throw new EchoError("E303", "The " + word + " condition must be true or false, not " + describe(v) + ".");
    }

    /** 'text "ATGX"', 'number 5', 'list' ... used in error messages. */
    public static String describe(Object v) {
        String t = type(v);
        if (v instanceof String || isNum(v)) {
            String s = show(v, true);
            if (s.length() > 24) s = s.substring(0, 21) + "...\"";
            return t + " " + s;
        }
        return t;
    }

    // ------------------------------------------------------------------ types
    private static final Map<String, String[][]> RECORDS = new HashMap<>();

    /** Checks a value against an Echo type such as "number", "list of dna" or "text or nothing". */
    public static Object typed(Object v, String spec, String what) {
        if (!matches(v, spec)) throw new EchoError("E302", what + " must be " + spec + ", but got " + describe(v) + ".");
        return v;
    }

    public static boolean matches(Object v, String spec) {
        if (spec == null) return true;
        if (spec.endsWith(" or nothing")) {
            if (v == null) return true;
            spec = spec.substring(0, spec.length() - " or nothing".length());
        }
        String of = null;
        int k = spec.indexOf(" of ");
        if (k > 0) { of = spec.substring(k + 4); spec = spec.substring(0, k); }
        switch (spec) {
            case "any": return true;
            case "nothing": return v == null;
            case "number": return isNum(v);
            case "integer": return isInt(v) || (v instanceof Double && (Double) v == Math.rint((Double) v));
            case "boolean": return v instanceof Boolean;
            case "text": return v instanceof String;
            case "dna": return v instanceof String && ((String) v).matches("[ACGTNacgtn]*");
            case "rna": return v instanceof String && ((String) v).matches("[ACGUNacgun]*");
            case "protein": return v instanceof String && ((String) v).matches("[ACDEFGHIKLMNPQRSTVWYXBZUOacdefghiklmnpqrstvwyxbzuo*]*");
            case "function": return v instanceof EchoFn;
            case "list":
                if (!(v instanceof List)) return false;
                if (of != null) for (Object o : (List<?>) v) if (!matches(o, of)) return false;
                return true;
            case "map":
                if (!(v instanceof Map) || ((Map<?, ?>) v).containsKey("_type")) return false;
                if (of != null) for (Object o : ((Map<?, ?>) v).values()) if (!matches(o, of)) return false;
                return true;
            default:
                return v instanceof Map && spec.equals(((Map<?, ?>) v).get("_type"));
        }
    }

    /** What `catch problem` receives: Error(code, message, line). */
    public static Object errorRecord(Throwable e) {
        LinkedHashMap<Object, Object> m = new LinkedHashMap<>();
        m.put("_type", "Error");
        m.put("code", e instanceof EchoError ? ((EchoError) e).code
                : e instanceof ArithmeticException ? "E401" : e instanceof StackOverflowError ? "E405" : "E404");
        m.put("message", message(e));
        m.put("line", null);
        return m;
    }

    // ------------------------------------------------------------------ items, fields, calls
    static int position(Object list, int size, Object key) {
        if (!isInt(key) && !(key instanceof Double && (Double) key == Math.rint((Double) key)))
            throw new EchoError("A position must be a whole number, not " + show(key, true) + ".");
        int k = (int) toLong(key);
        if (k < -size || k >= size)
            throw new EchoError("Position " + k + " is outside (it has " + size + " item" + (size == 1 ? "" : "s")
                    + "; positions start at 0).");
        return k < 0 ? size + k : k;
    }

    public static Object index(Object obj, Object key) {
        if (obj instanceof List) { List<?> l = (List<?>) obj; return l.get(position(obj, l.size(), key)); }
        if (obj instanceof String) { String s = (String) obj; int i = position(obj, s.length(), key); return s.substring(i, i + 1); }
        if (obj instanceof Map) {
            Map<?, ?> m = (Map<?, ?>) obj;
            if (!m.containsKey(key)) throw new EchoError("The map has no key " + show(key, true) + ".");
            return m.get(key);
        }
        throw new EchoError("Can't take an item from " + type(obj) + ".");
    }

    @SuppressWarnings("unchecked")
    public static void setIndex(Object obj, Object key, Object value) {
        if (obj instanceof List) { List<Object> l = (List<Object>) obj; l.set(position(obj, l.size(), key), value); return; }
        if (obj instanceof Map) { ((Map<Object, Object>) obj).put(key, value); return; }
        throw new EchoError("You can only change items of a list or map, not " + type(obj) + ".");
    }

    static int sliceIdx(Object v, int n, int def) {
        if (v == null) return def;
        int i = (int) toLong(v);
        if (i < 0) i += n;
        return Math.max(0, Math.min(n, i));
    }

    public static Object slice(Object obj, Object a, Object b) {
        if (obj instanceof String) {
            String s = (String) obj; int x = sliceIdx(a, s.length(), 0), y = sliceIdx(b, s.length(), s.length());
            return x >= y ? "" : s.substring(x, y);
        }
        if (obj instanceof List) {
            List<?> l = (List<?>) obj; int x = sliceIdx(a, l.size(), 0), y = sliceIdx(b, l.size(), l.size());
            return x >= y ? new ArrayList<>() : new ArrayList<>(l.subList(x, y));
        }
        throw new EchoError("Can only slice text or lists.");
    }

    public static Object attr(Object obj, String name) {
        if (obj instanceof Map && ((Map<?, ?>) obj).containsKey(name) && !"_type".equals(name))
            return ((Map<?, ?>) obj).get(name);
        throw new EchoError("E202", (obj instanceof Map && ((Map<?, ?>) obj).get("_type") != null
                ? ((Map<?, ?>) obj).get("_type") : type(obj)) + " has no field '" + name + "'.");
    }

    @SuppressWarnings("unchecked")
    public static void setAttr(Object obj, String name, Object value) {
        if (!(obj instanceof Map)) throw new EchoError("E301", "Only maps and records have fields you can set, not " + type(obj) + ".");
        Object t = ((Map<?, ?>) obj).get("_type");
        String[][] rec = t == null ? null : RECORDS.get(t);
        if (rec != null) {
            int i = Arrays.asList(rec[0]).indexOf(name);
            if (i < 0) throw new EchoError("E202", "Record " + t + " has no field '" + name + "'.");
            if (rec[1][i] != null) typed(value, rec[1][i], "Field " + t + "." + name);
        }
        ((Map<Object, Object>) obj).put(name, value);
    }

    public static Object call(Object f, Object... args) {
        if (f instanceof EchoFn) return ((EchoFn) f).call(args);
        throw new EchoError(show(f, true) + " is not a function, so it can't be called.");
    }

    private static final Map<String, Method> METHODS = new HashMap<>();

    /** A built-in function as a value, e.g. map(list, fn("upper")). Null if no such built-in. */
    public static EchoFn fn(String name) {
        synchronized (METHODS) {
            if (METHODS.isEmpty()) {
                for (Method m : EchoRuntime.class.getDeclaredMethods()) {
                    if (Modifier.isPublic(m.getModifiers()) && Modifier.isStatic(m.getModifiers())
                            && m.getParameterCount() == 1 && m.getParameterTypes()[0] == Object[].class)
                        METHODS.put(m.getName().endsWith("_") ? m.getName().substring(0, m.getName().length() - 1) : m.getName(), m);
                }
            }
        }
        final Method m = METHODS.get(name);
        if (m == null) return null;
        return named(name, a -> {
            try { return m.invoke(null, (Object) a); }
            catch (java.lang.reflect.InvocationTargetException e) {
                if (e.getCause() instanceof RuntimeException) throw (RuntimeException) e.getCause();
                throw new EchoError(String.valueOf(e.getCause()));
            } catch (IllegalAccessException e) { throw new EchoError(e.toString()); }
        });
    }

    public static EchoFn record(final String name, final String[] fields, final Object[] defaults, final String[] types) {
        RECORDS.put(name, new String[][]{fields, types});
        return named(name, a -> {
            int positional = 0;
            for (Object o : a) if (!(o instanceof Kw)) positional++;
            if (positional > fields.length)
                throw new EchoError("E203", name + "() takes " + fields.length + " value" + (fields.length == 1 ? "" : "s") + " but got " + positional + ".");
            LinkedHashMap<Object, Object> m = new LinkedHashMap<>();
            m.put("_type", name);
            for (int i = 0; i < fields.length; i++) {
                Object v = arg(a, i, fields[i], MISSING);
                if (v == MISSING) {
                    if (defaults[i] == MISSING) throw new EchoError("E205", name + "() is missing the value for '" + fields[i] + "'.");
                    v = defaults[i];
                }
                if (types[i] != null) typed(v, types[i], "Field " + name + "." + fields[i]);
                m.put(fields[i], v);
            }
            return m;
        });
    }

    /** Marks a record field without a default. */
    public static final Object NO_DEFAULT = MISSING;

    /** Gives a fn(...) -> ... the values it uses from the surrounding function. */
    public static EchoFn capture(Object[] values, java.util.function.Function<Object[], EchoFn> make) {
        return make.apply(values);
    }

    public static Object addTo(Object target, Object value) {
        if (target instanceof List) { @SuppressWarnings("unchecked") List<Object> l = (List<Object>) target; l.add(value); return l; }
        throw new EchoError("E301", "'add ... to' needs a list, not " + type(target) + ".");
    }

    public static Iterable<Object> iter(Object v) {
        ArrayList<Object> out = new ArrayList<>();
        if (v instanceof Map) { for (Object k : ((Map<?, ?>) v).keySet()) if (!"_type".equals(k)) out.add(k); }
        else if (v instanceof List) out.addAll((List<?>) v);
        else if (v instanceof String) for (char c : ((String) v).toCharArray()) out.add(String.valueOf(c));
        else if (isNum(v)) for (long i = 0; i < toLong(v); i++) out.add(i);
        else throw new EchoError("Can't loop over " + type(v) + ".");
        return out;
    }

    public static Iterable<Object[]> pairs(Object v) {
        ArrayList<Object[]> out = new ArrayList<>();
        if (v instanceof Map) { for (Map.Entry<?, ?> e : ((Map<?, ?>) v).entrySet())
            if (!"_type".equals(e.getKey())) out.add(new Object[]{e.getKey(), e.getValue()}); }
        else { long i = 0; for (Object o : iter(v)) out.add(new Object[]{i++, o}); }
        return out;
    }

    /** Echo `for i from a to b step s`: b included. */
    public static Iterable<Object> loopRange(Object a, Object b, Object step) {
        if (!isNum(a) || !isNum(b)) throw new EchoError("The loop start and end must be numbers.");
        boolean ints = isInt(a) && isInt(b) && (step == null || isInt(step));
        double s = step == null ? (toDouble(b) >= toDouble(a) ? 1 : -1) : toDouble(step);
        if (s == 0) throw new EchoError("step can't be 0.");
        ArrayList<Object> out = new ArrayList<>();
        for (double i = toDouble(a); s > 0 ? i <= toDouble(b) + 1e-12 : i >= toDouble(b) - 1e-12; i += s) {
            out.add(ints ? (Object) (long) Math.round(i) : (Object) i);
            if (out.size() > 50_000_000) throw new EchoError("The loop is too big.");
        }
        return out;
    }

    public static String message(Throwable e) {
        if (e instanceof EchoError) return e.getMessage();
        if (e instanceof ArithmeticException) return "Division by zero.";
        if (e instanceof StackOverflowError) return "Too much recursion.";
        return String.valueOf(e.getMessage());
    }

    // ================================================================== built-ins (Object... args)
    // ---------- core
    public static Object say(Object... a) {
        StringBuilder b = new StringBuilder();
        for (int i = 0; i < a.length; i++) { if (i > 0) b.append(' '); b.append(show(a[i])); }
        out.line(b.toString());
        return null;
    }

    public static Object print(Object... a) { return say(a); }

    public static Object ask(Object prompt) {
        String s = in.read(show(prompt) + " ");
        if (s == null) s = "";
        String t = s.trim();
        try { return Long.parseLong(t); } catch (NumberFormatException ignored) {}
        try { if (!t.isEmpty() && "+-.0123456789".indexOf(t.charAt(0)) >= 0) return Double.parseDouble(t); }
        catch (NumberFormatException ignored) {}
        return s;
    }

    public static Object input(Object... a) { return in.read(show(arg(a, 0, "prompt", ""))); }

    public static Object type(Object... a) { return type(req(a, 0, "x", "type")); }

    public static Object length(Object... a) {
        Object v = req(a, 0, "x", "length");
        if (v instanceof String) return (long) ((String) v).length();
        if (v instanceof List) return (long) ((List<?>) v).size();
        if (v instanceof Map) { long n = 0; for (Object k : ((Map<?, ?>) v).keySet()) if (!"_type".equals(k)) n++; return n; }
        throw new EchoError("length() needs text, a list or a map, not " + type(v) + ".");
    }

    public static Object len(Object... a) { return length(a); }
    public static Object size(Object... a) { return length(a); }
    public static Object text(Object... a) { return show(arg(a, 0)); }

    public static Object number(Object... a) {
        Object v = arg(a, 0);
        if (v instanceof Boolean) return ((Boolean) v) ? 1L : 0L;
        if (isNum(v)) return v;
        String s = show(v).trim();
        try { return Long.parseLong(s); } catch (NumberFormatException ignored) {}
        try { return Double.parseDouble(s); } catch (NumberFormatException e) { throw new EchoError("'" + s + "' is not a number."); }
    }

    public static Object int_(Object... a) { Object n = number(a); return isInt(n) ? n : (Object) (long) toDouble(n); }
    public static Object abs(Object... a) { Object v = arg(a, 0); return isInt(v) ? (Object) Math.abs(toLong(v)) : (Object) Math.abs(toDouble(v)); }

    public static Object round(Object... a) {
        double x = toDouble(arg(a, 0, "x", 0L)); long p = toLong(arg(a, 1, "places", 0L));
        if (p == 0) return (long) Math.floor(x + 0.5);
        return new BigDecimal(x).setScale((int) p, java.math.RoundingMode.HALF_EVEN).doubleValue();
    }

    public static Object floor(Object... a) { return (long) Math.floor(toDouble(arg(a, 0))); }
    public static Object ceil(Object... a) { return (long) Math.ceil(toDouble(arg(a, 0))); }

    public static Object sqrt(Object... a) {
        double x = toDouble(arg(a, 0));
        if (x < 0) throw new EchoError("sqrt() of a negative number.");
        double r = Math.sqrt(x);
        return r == Math.rint(r) ? (Object) (long) r : (Object) r;
    }

    static List<?> items(Object[] a, String fn) {
        if (a.length == 1 && a[0] instanceof List) return (List<?>) a[0];
        return Arrays.asList(a);
    }

    public static Object min(Object... a) {
        List<?> l = items(a, "min"); if (l.isEmpty()) throw new EchoError("min() of an empty list.");
        Object best = l.get(0); for (Object o : l) if (cmp(o, best) < 0) best = o; return best;
    }

    public static Object max(Object... a) {
        List<?> l = items(a, "max"); if (l.isEmpty()) throw new EchoError("max() of an empty list.");
        Object best = l.get(0); for (Object o : l) if (cmp(o, best) > 0) best = o; return best;
    }

    public static Object sum(Object... a) { Object s = 0L; for (Object o : items(a, "sum")) s = add(s, o); return s; }
    public static Object random(Object... a) { return RNG.nextDouble(); }

    public static Object random_int(Object... a) {
        long lo = toLong(arg(a, 0)), hi = toLong(arg(a, 1));
        return lo + (long) Math.floor(RNG.nextDouble() * (hi - lo + 1));
    }

    public static Object choose(Object... a) { List<?> l = (List<?>) arg(a, 0); return l.get(RNG.nextInt(l.size())); }

    public static Object range(Object... a) {
        Object x = arg(a, 0), y = arg(a, 1, "b", null), s = arg(a, 2, "step", 1L);
        if (y == null) { y = sub(x, 1L); x = 0L; }
        ArrayList<Object> out = new ArrayList<>();
        for (Object o : loopRange(x, y, s)) out.add(o);
        return out;
    }

    @SuppressWarnings("unchecked")
    public static Object append(Object... a) { List<Object> l = (List<Object>) arg(a, 0); l.add(arg(a, 1)); return l; }
    public static Object push(Object... a) { return append(a); }

    @SuppressWarnings("unchecked")
    public static Object pop(Object... a) {
        List<Object> l = (List<Object>) arg(a, 0);
        if (l.isEmpty()) throw new EchoError("pop() from an empty list.");
        return l.remove(position(l, l.size(), arg(a, 1, "position", -1L)));
    }

    @SuppressWarnings("unchecked")
    public static Object insert(Object... a) { List<Object> l = (List<Object>) arg(a, 0); l.add((int) toLong(arg(a, 1)), arg(a, 2)); return l; }

    public static Object remove(Object... a) {
        Object c = arg(a, 0), v = arg(a, 1);
        if (c instanceof Map) ((Map<?, ?>) c).remove(v); else if (c instanceof List) ((List<?>) c).remove(v);
        return c;
    }

    public static Object sort(Object... a) {
        ArrayList<Object> l = new ArrayList<>((List<?>) arg(a, 0));
        final Object key = arg(a, 1, "key", null);
        boolean rev = truthy(arg(a, 2, "reverse", false));
        Comparator<Object> c = key == null ? EchoRuntime::cmp : (x, y) -> cmp(call(key, x), call(key, y));
        l.sort(rev ? c.reversed() : c);
        return l;
    }

    public static Object reverse(Object... a) {
        Object v = arg(a, 0);
        if (v instanceof String) return new StringBuilder((String) v).reverse().toString();
        ArrayList<Object> l = new ArrayList<>((List<?>) v); Collections.reverse(l); return l;
    }

    public static Object map(Object... a) {
        ArrayList<Object> out = new ArrayList<>(); Object f = arg(a, 1);
        for (Object o : iter(arg(a, 0))) out.add(call(f, o));
        return out;
    }

    public static Object filter(Object... a) {
        ArrayList<Object> out = new ArrayList<>(); Object f = arg(a, 1);
        for (Object o : iter(arg(a, 0))) if (truthy(call(f, o))) out.add(o);
        return out;
    }

    public static Object reduce(Object... a) {
        List<?> l = (List<?>) arg(a, 0); Object f = arg(a, 1); Object acc = arg(a, 2, "start", null);
        int i = 0;
        if (acc == null) { if (l.isEmpty()) throw new EchoError("reduce() of an empty list needs a start value."); acc = l.get(0); i = 1; }
        for (; i < l.size(); i++) acc = call(f, acc, l.get(i));
        return acc;
    }

    public static Object unique(Object... a) {
        ArrayList<Object> out = new ArrayList<>();
        for (Object o : (List<?>) arg(a, 0)) if (!in(o, out)) out.add(o);
        return out;
    }

    public static Object join(Object... a) {
        StringBuilder b = new StringBuilder(); String sep = show(arg(a, 1, "separator", ""));
        boolean first = true;
        for (Object o : (List<?>) arg(a, 0)) { if (!first) b.append(sep); first = false; b.append(show(o)); }
        return b.toString();
    }

    public static Object split(Object... a) {
        String s = show(arg(a, 0)); Object sep = arg(a, 1, "separator", null);
        ArrayList<Object> out = new ArrayList<>();
        if (sep == null) { for (String p : s.trim().split("\\s+")) if (!p.isEmpty()) out.add(p); }
        else if ("".equals(sep)) { for (char c : s.toCharArray()) out.add(String.valueOf(c)); }
        else out.addAll(Arrays.asList(s.split(Pattern.quote(show(sep)), -1)));
        return out;
    }

    public static Object upper(Object... a) { return show(arg(a, 0)).toUpperCase(); }
    public static Object lower(Object... a) { return show(arg(a, 0)).toLowerCase(); }
    public static Object trim(Object... a) { return show(arg(a, 0)).trim(); }
    public static Object replace(Object... a) { return show(arg(a, 0)).replace(show(arg(a, 1)), show(arg(a, 2))); }
    public static Object contains(Object... a) { return in(arg(a, 1), arg(a, 0)); }
    public static Object starts_with(Object... a) { return show(arg(a, 0)).startsWith(show(arg(a, 1))); }
    public static Object ends_with(Object... a) { return show(arg(a, 0)).endsWith(show(arg(a, 1))); }
    public static Object find(Object... a) { return (long) show(arg(a, 0)).indexOf(show(arg(a, 1))); }

    public static Object index_of(Object... a) {
        Object c = arg(a, 0), v = arg(a, 1);
        if (c instanceof String) return (long) ((String) c).indexOf(show(v));
        List<?> l = (List<?>) c; for (int i = 0; i < l.size(); i++) if (eq(l.get(i), v)) return (long) i; return -1L;
    }

    public static Object count(Object... a) {
        Object c = arg(a, 0), v = arg(a, 1); long n = 0;
        if (c instanceof String) { String s = (String) c, t = show(v); if (t.isEmpty()) return 0L;
            for (int i = s.indexOf(t); i >= 0; i = s.indexOf(t, i + t.length())) n++; return n; }
        for (Object o : (List<?>) c) if (eq(o, v)) n++;
        return n;
    }

    public static Object format(Object... a) {
        return String.format(Locale.ROOT, "%." + toLong(arg(a, 1, "places", 2L)) + "f", toDouble(arg(a, 0)));
    }

    public static Object keys(Object... a) { return new ArrayList<Object>((Collection<?>) iter(arg(a, 0))); }

    public static Object values(Object... a) {
        ArrayList<Object> out = new ArrayList<>();
        for (Map.Entry<?, ?> e : ((Map<?, ?>) arg(a, 0)).entrySet()) if (!"_type".equals(e.getKey())) out.add(e.getValue());
        return out;
    }

    public static Object has(Object... a) { return ((Map<?, ?>) arg(a, 0)).containsKey(arg(a, 1)); }

    public static Object get(Object... a) {
        Object c = arg(a, 0), k = arg(a, 1), d = arg(a, 2, "default", null);
        if (c instanceof Map) { Map<?, ?> m = (Map<?, ?>) c; return m.containsKey(k) ? m.get(k) : d; }
        try { return index(c, k); } catch (RuntimeException e) { return d; }
    }

    public static Object now(Object... a) { return new SimpleDateFormat("yyyy-MM-dd HH:mm:ss", Locale.ROOT).format(new Date()); }
    public static Object today(Object... a) { return new SimpleDateFormat("yyyy-MM-dd", Locale.ROOT).format(new Date()); }

    public static final Object pi = Math.PI;
    public static final Object e = Math.E;

    // ---------- bio
    static final String CODON_AAS = "FFLLSSSSYY**CC*WLLLLPPPPHHQQRRRRIIIMTTTTNNKKSSRRVVVVAAAADDEEGGGG";
    static final Map<String, Character> CODONS = new HashMap<>();
    static {
        String b = "TCAG"; int i = 0;
        for (char x : b.toCharArray()) for (char y : b.toCharArray()) for (char z : b.toCharArray())
            CODONS.put("" + x + y + z, CODON_AAS.charAt(i++));
    }
    public static final Object start_codon = "ATG";
    public static final Object stop_codons = list("TAA", "TAG", "TGA");

    static String seq(Object v, String fn) {
        if (v instanceof Map && ((Map<?, ?>) v).containsKey("seq")) v = ((Map<?, ?>) v).get("seq");
        if (!(v instanceof String)) throw new EchoError(fn + "() needs a DNA sequence as text.");
        StringBuilder b = new StringBuilder();
        for (String line : ((String) v).split("\n")) if (!line.startsWith(">")) b.append(line);
        String s = b.toString().replaceAll("[\\s\\d]", "").toUpperCase().replace('U', 'T');
        Matcher m = Pattern.compile("[^ACGTRYSWKMBDHVN]").matcher(s);
        if (m.find()) throw new EchoError(fn + ": '" + m.group() + "' is not a DNA letter.");
        return s;
    }

    public static Object dna(Object... a) { return seq(arg(a, 0), "dna"); }

    public static Object gc(Object... a) {
        String s = seq(arg(a, 0), "gc"); if (s.isEmpty()) return 0L;
        int n = 0; for (char c : s.toCharArray()) if (c == 'G' || c == 'C' || c == 'S') n++;
        return round2(100.0 * n / s.length());
    }

    public static Object gc_content(Object... a) { return gc(a); }

    public static Object at(Object... a) {
        String s = seq(arg(a, 0), "at"); if (s.isEmpty()) return 0L;
        int n = 0; for (char c : s.toCharArray()) if (c == 'A' || c == 'T' || c == 'W') n++;
        return round2(100.0 * n / s.length());
    }

    static Object round2(double d) {
        double r = Math.round(d * 100.0) / 100.0;
        return r == Math.rint(r) ? (Object) (double) r : (Object) r;
    }

    public static Object gc_count(Object... a) {
        long n = 0; for (char c : seq(arg(a, 0), "gc_count").toCharArray()) if (c == 'G' || c == 'C') n++; return n;
    }

    public static Object base_counts(Object... a) {
        String s = seq(arg(a, 0), "base_counts");
        LinkedHashMap<Object, Object> m = new LinkedHashMap<>(); long other = s.length();
        for (char c : "ACGT".toCharArray()) { long n = s.chars().filter(x -> x == c).count(); m.put(String.valueOf(c), n); other -= n; }
        if (other > 0) m.put("other", other);
        return m;
    }

    static char comp(char c) {
        switch (c) {
            case 'A': return 'T'; case 'T': return 'A'; case 'G': return 'C'; case 'C': return 'G';
            case 'R': return 'Y'; case 'Y': return 'R'; case 'K': return 'M'; case 'M': return 'K';
            case 'B': return 'V'; case 'V': return 'B'; case 'D': return 'H'; case 'H': return 'D';
            default: return c;
        }
    }

    public static Object complement(Object... a) {
        StringBuilder b = new StringBuilder(); for (char c : seq(arg(a, 0), "complement").toCharArray()) b.append(comp(c));
        return b.toString();
    }

    public static Object reverse_complement(Object... a) { return new StringBuilder((String) complement(a)).reverse().toString(); }
    public static Object revcomp(Object... a) { return reverse_complement(a); }
    public static Object transcribe(Object... a) { return seq(arg(a, 0), "transcribe").replace('T', 'U'); }
    public static Object back_transcribe(Object... a) { return seq(arg(a, 0), "back_transcribe"); }

    public static Object translate(Object... a) {
        String s = seq(arg(a, 0), "translate");
        long frame = toLong(arg(a, 1, "frame", 1L));
        boolean toStop = truthy(arg(a, 2, "to_stop", false));
        if (frame < 0) { s = (String) reverse_complement(s); frame = -frame; }
        if (frame < 1 || frame > 3) throw new EchoError("frame must be 1, 2 or 3 (or -1, -2, -3 for the other strand).");
        StringBuilder b = new StringBuilder();
        for (int i = (int) frame - 1; i + 3 <= s.length(); i += 3) {
            Character aa = CODONS.get(s.substring(i, i + 3)); char c = aa == null ? 'X' : aa;
            if (c == '*' && toStop) break;
            b.append(c);
        }
        return b.toString();
    }

    public static Object find_orfs(Object... a) {
        String s = seq(arg(a, 0), "find_orfs"); long minAa = toLong(arg(a, 1, "min_aa", 30L));
        int n = s.length();
        ArrayList<Object> found = new ArrayList<>();
        String[] strands = {s, (String) reverse_complement(s)};
        for (int st = 0; st < 2; st++) {
            String q = strands[st];
            for (int frame = 0; frame < 3; frame++) {
                int i = frame;
                while (i <= q.length() - 3) {
                    if (q.startsWith("ATG", i)) {
                        int j = i;
                        while (j <= q.length() - 3 && !Character.valueOf('*').equals(CODONS.get(q.substring(j, j + 3)))) j += 3;
                        if (j <= q.length() - 3) {
                            String prot = (String) translate(q.substring(i, j));
                            if (prot.length() >= minAa) {
                                long start = st == 0 ? i + 1 : n - (j + 3) + 1, end = st == 0 ? j + 3 : n - i;
                                found.add(mapOf("strand", st == 0 ? "+" : "-", "frame", (long) frame + 1, "start", start,
                                        "end", end, "length_bp", (long) (j + 3 - i), "protein", prot));
                            }
                            i = j + 3; continue;
                        }
                    }
                    i += 3;
                }
            }
        }
        found.sort((x, y) -> Long.compare(toLong(((Map<?, ?>) y).get("length_bp")), toLong(((Map<?, ?>) x).get("length_bp"))));
        return found;
    }

    static final Map<Character, String> IUPAC = new HashMap<>();
    static {
        String[][] t = {{"A", "A"}, {"C", "C"}, {"G", "G"}, {"T", "T"}, {"R", "AG"}, {"Y", "CT"}, {"S", "CG"}, {"W", "AT"},
                {"K", "GT"}, {"M", "AC"}, {"B", "CGT"}, {"D", "AGT"}, {"H", "ACT"}, {"V", "ACG"}, {"N", "ACGT"}};
        for (String[] r : t) IUPAC.put(r[0].charAt(0), r[1]);
    }

    public static Object find_motif(Object... a) {
        String s = seq(arg(a, 0), "find_motif"), m = seq(arg(a, 1), "find_motif");
        StringBuilder p = new StringBuilder("(?=");
        for (char c : m.toCharArray()) { String o = IUPAC.get(c); p.append(o.length() > 1 ? "[" + o + "]" : o); }
        Matcher mt = Pattern.compile(p.append(")").toString()).matcher(s);
        ArrayList<Object> out = new ArrayList<>();
        while (mt.find()) out.add((long) mt.start() + 1);
        return out;
    }

    public static Object hamming(Object... a) {
        String x = seq(arg(a, 0), "hamming"), y = seq(arg(a, 1), "hamming");
        if (x.length() != y.length()) throw new EchoError("hamming() needs sequences of the same length.");
        long n = 0; for (int i = 0; i < x.length(); i++) if (x.charAt(i) != y.charAt(i)) n++; return n;
    }

    public static Object mutate(Object... a) {
        String s = seq(arg(a, 0), "mutate"); int p = (int) toLong(arg(a, 1));
        if (p < 1 || p > s.length()) throw new EchoError("Position " + p + " is outside the sequence (1 to " + s.length() + ").");
        return s.substring(0, p - 1) + seq(arg(a, 2), "mutate") + s.substring(p);
    }

    // nearest-neighbour Tm (Allawi & SantaLucia; Na+ 50 mM; primer 25 nM) — same as Biopython Tm_NN defaults
    static final Map<String, double[]> NN = new HashMap<>();
    static {
        Object[][] t = {{"AA/TT", -7.9, -22.2}, {"AT/TA", -7.2, -20.4}, {"TA/AT", -7.2, -21.3}, {"CA/GT", -8.5, -22.7},
                {"GT/CA", -8.4, -22.4}, {"CT/GA", -7.8, -21.0}, {"GA/CT", -8.2, -22.2}, {"CG/GC", -10.6, -27.2},
                {"GC/CG", -9.8, -24.4}, {"GG/CC", -8.0, -19.9}};
        for (Object[] r : t) NN.put((String) r[0], new double[]{(Double) r[1], (Double) r[2]});
    }

    public static double tmNN(String s, double na, double primerNm) {
        s = s.replace("N", "");
        if (s.length() < 2) throw new EchoError("tm() needs at least 2 bases.");
        if (!s.matches("[ACGT]+")) {
            StringBuilder lo = new StringBuilder(), hi = new StringBuilder();
            for (char c : s.toCharArray()) {
                String o = IUPAC.getOrDefault(c, "ACGT");
                lo.append(o.length() == 1 ? o.charAt(0) : o.indexOf('A') >= 0 ? 'A' : o.indexOf('T') >= 0 ? 'T' : o.charAt(0));
                hi.append(o.length() == 1 ? o.charAt(0) : o.indexOf('G') >= 0 ? 'G' : o.indexOf('C') >= 0 ? 'C' : o.charAt(0));
            }
            return (tmNN(lo.toString(), na, primerNm) + tmNN(hi.toString(), na, primerNm)) / 2;
        }
        double dh = 0, ds = 0;
        for (char end : new char[]{s.charAt(0), s.charAt(s.length() - 1)}) {
            if (end == 'A' || end == 'T') { dh += 2.3; ds += 4.1; } else { dh += 0.1; ds += -2.8; }
        }
        for (int i = 0; i < s.length() - 1; i++) {
            String key = s.substring(i, i + 2) + "/" + comp(s.charAt(i)) + comp(s.charAt(i + 1));
            double[] v = NN.get(key);
            if (v == null) v = NN.get(new StringBuilder(key).reverse().toString());
            dh += v[0]; ds += v[1];
        }
        double k = (primerNm - primerNm / 2) * 1e-9;
        ds += 0.368 * (s.length() - 1) * Math.log(na * 1e-3);
        return (1000 * dh) / (ds + 1.987 * Math.log(k)) - 273.15;
    }

    public static Object tm(Object... a) {
        return Math.round(tmNN(seq(arg(a, 0), "tm"), toDouble(arg(a, 1, "na", 50L)), toDouble(arg(a, 2, "primer_nm", 25L))) * 100.0) / 100.0;
    }

    public static Object tm_basic(Object... a) {
        long n = 0; for (char c : seq(arg(a, 0), "tm_basic").toCharArray()) n += (c == 'G' || c == 'C') ? 4 : 2; return n;
    }

    static boolean pairs(char a, char b) { return comp(a) == b && "ACGT".indexOf(a) >= 0; }

    static int[] dimer(String a, String b) {
        int best = 0; boolean at3 = false;
        String br = new StringBuilder(b).reverse().toString();
        for (int shift = -br.length() + 1; shift < a.length(); shift++) {
            int run = 0;
            for (int i = 0; i <= a.length(); i++) {
                int j = i - shift;
                boolean ok = i < a.length() && j >= 0 && j < br.length() && pairs(a.charAt(i), br.charAt(j));
                if (ok) run++;
                else if (run > 0) {
                    int endI = i - 1, startJ = (i - run) - shift;
                    boolean t = endI >= a.length() - 2 || startJ <= 1;
                    if (run > best || (run == best && t && !at3)) { best = run; at3 = t; }
                    run = 0;
                }
            }
        }
        return new int[]{best, at3 ? 1 : 0};
    }

    static int hairpin(String s) {
        int best = 0;
        for (int i = 0; i < s.length(); i++)
            for (int j = s.length() - 1; j > i + 3; j--) {
                int k = 0;
                while (i + k < j - k - 3 && pairs(s.charAt(i + k), s.charAt(j - k))) k++;
                best = Math.max(best, k);
            }
        return best;
    }

    static int longestRun(String s) {
        int best = s.isEmpty() ? 0 : 1, cur = 1;
        for (int i = 1; i < s.length(); i++) { cur = s.charAt(i) == s.charAt(i - 1) ? cur + 1 : 1; best = Math.max(best, cur); }
        return best;
    }

    static double gcPct(String s) {
        int n = 0; for (char c : s.toCharArray()) if (c == 'G' || c == 'C' || c == 'S') n++;
        return Math.round(10000.0 * n / s.length()) / 100.0;
    }

    static ArrayList<Object> problems(String p) {
        ArrayList<Object> out = new ArrayList<>();
        double g = gcPct(p), t = tmNN(p, 50, 25);
        if (p.length() < 18 || p.length() > 30) out.add("length " + p.length() + " nt (18-30 is usual)");
        if (g < 40 || g > 60) out.add(String.format(Locale.ROOT, "GC %.0f%% (aim 40-60%%)", g));
        if (t < 52 || t > 65) out.add(String.format(Locale.ROOT, "Tm %.1f °C (aim 52-65)", t));
        if ("GC".indexOf(p.charAt(p.length() - 1)) < 0) out.add("no G/C clamp at the 3' end");
        int e = 0; for (char c : p.substring(Math.max(0, p.length() - 5)).toCharArray()) if (c == 'G' || c == 'C') e++;
        if (e > 3) out.add("more than 3 G/C in the last 5 bases");
        if (longestRun(p) >= 4) out.add("a run of 4 or more of the same base");
        if (hairpin(p) >= 4) out.add("possible hairpin");
        int[] d = dimer(p, p);
        if (d[0] >= 4 && d[1] == 1) out.add("self-dimer at the 3' end");
        return out;
    }

    public static Object primer_check(Object... a) { return problems(seq(arg(a, 0), "primer_check")); }

    public static Object primer_info(Object... a) {
        String p = seq(arg(a, 0), "primer_info");
        return mapOf("seq", p, "length", (long) p.length(), "gc", gcPct(p), "gc_count", gc_count(p),
                "tm", Math.round(tmNN(p, 50, 25) * 100.0) / 100.0, "problems", problems(p));
    }

    public static Object design_primers(Object... a) {
        final String s = seq(arg(a, 0), "design_primers");
        long pmin = toLong(arg(a, 1, "product_min", 100L)), pmax = toLong(arg(a, 2, "product_max", 1000L));
        final double opt = toDouble(arg(a, 3, "tm_opt", 60L)), gmin = toDouble(arg(a, 4, "gc_min", 40L)), gmax = toDouble(arg(a, 5, "gc_max", 60L));
        if (s.length() < 60) throw new EchoError("design_primers() needs at least 60 bases.");
        if (pmin > s.length()) throw new EchoError("The sequence (" + s.length() + " bp) is shorter than product_min (" + pmin + ").");
        List<double[]> fs = scanPrimers(s, true, opt, gmin, gmax), rs = scanPrimers(s, false, opt, gmin, gmax);
        double[] bf = null, br = null; double bestScore = Double.MAX_VALUE; long bestSize = 0;
        for (double[] f : fs) for (double[] r : rs) {
            long size = (long) (r[1] + r[2] - f[1]);
            if (r[1] < f[1] + f[2] || size < pmin || size > pmax) continue;
            String fp = primerAt(s, f, true), rp = primerAt(s, r, false);
            double d = Math.abs(f[4] - r[4]);
            int[] x = dimer(fp, rp);
            double sc = f[0] + r[0] + d * 1.5 + (d > 3 ? 10 : 0) + (x[0] >= 4 && x[1] == 1 ? 8 : 0);
            if (sc < bestScore) { bestScore = sc; bf = f; br = r; bestSize = size; }
        }
        if (bf == null) throw new EchoError("No primer pair fits. Try a wider product size.");
        String fp = primerAt(s, bf, true), rp = primerAt(s, br, false);
        ArrayList<Object> probs = problems(fp);
        for (Object o : problems(rp)) probs.add("reverse: " + o);
        return mapOf("forward", fp, "reverse", rp, "product", bestSize, "forward_start", (long) bf[1] + 1,
                "reverse_end", (long) (br[1] + br[2]), "tm_forward", Math.round(bf[4] * 100.0) / 100.0,
                "tm_reverse", Math.round(br[4] * 100.0) / 100.0, "gc_forward", bf[3], "gc_reverse", br[3], "problems", probs);
    }

    static String primerAt(String s, double[] c, boolean forward) {
        String top = s.substring((int) c[1], (int) (c[1] + c[2]));
        return forward ? top : (String) reverse_complement(top);
    }

    /** returns rows of {score, start, length, gc, tm} */
    static List<double[]> scanPrimers(String s, boolean forward, double opt, double gmin, double gmax) {
        ArrayList<double[]> c = new ArrayList<>();
        for (int st = 0; st < s.length(); st++)
            for (int L = 18; L <= 25 && st + L <= s.length(); L++) {
                double[] row = {0, st, L, 0, 0};
                String p = primerAt(s, row, forward);
                if (p.indexOf('N') >= 0) continue;
                double g = gcPct(p), t = tmNN(p, 50, 25), sc = Math.abs(t - opt);
                if (g < gmin) sc += 10 + gmin - g; else if (g > gmax) sc += 10 + g - gmax;
                if ("GC".indexOf(p.charAt(p.length() - 1)) < 0) sc += 2;
                int e = 0; for (char ch : p.substring(p.length() - 5).toCharArray()) if (ch == 'G' || ch == 'C') e++;
                if (e > 3) sc += 4;
                row[0] = sc; row[3] = g; row[4] = t;
                c.add(row);
            }
        c.sort(Comparator.comparingDouble((double[] r) -> r[0]).thenComparingDouble(r -> r[1]).thenComparingDouble(r -> r[2]));
        List<double[]> shortList = new ArrayList<>(c.subList(0, Math.min(300, c.size())));
        for (double[] r : shortList) {
            String p = primerAt(s, r, forward);
            if (longestRun(p) >= 4) r[0] += 6;
            if (hairpin(p) >= 4) r[0] += 5;
            int[] d = dimer(p, p);
            if (d[0] >= 4 && d[1] == 1) r[0] += 6;
        }
        shortList.sort(Comparator.comparingDouble((double[] r) -> r[0]).thenComparingDouble(r -> r[1]).thenComparingDouble(r -> r[2]));
        return shortList.subList(0, Math.min(80, shortList.size()));
    }

    public static Object pcr_program(Object... a) {
        String f = seq(arg(a, 0), "pcr_program"), r = seq(arg(a, 1), "pcr_program");
        long bp = toLong(arg(a, 2, "product_bp", 500L));
        String pol = show(arg(a, 3, "polymerase", "taq")).toLowerCase();
        boolean hifi = pol.equals("hifi") || pol.equals("phusion") || pol.equals("q5") || pol.equals("high-fidelity");
        double low = Math.min(tmNN(f, 50, 25), tmNN(r, 50, 25));
        long ta = Math.round(hifi ? Math.min(low + 3, 72) : low - 5);
        int rate = hifi ? 30 : 60;
        int ext = Math.max(15, (int) (Math.ceil(bp / 1000.0 * rate / 5.0) * 5));
        String extT = ext < 60 ? ext + " s" : (ext / 60) + " min" + (ext % 60 != 0 ? " " + (ext % 60) + " s" : "");
        String[][] rows = {
                {"Initial denaturation", hifi ? "98 °C" : "95 °C", hifi ? "30 s" : "3 min", "1"},
                {"Denaturation", hifi ? "98 °C" : "95 °C", hifi ? "10 s" : "30 s", "30-35"},
                {"Annealing", ta + " °C", hifi ? "20 s" : "30 s", ""},
                {"Extension", "72 °C", extT, ""},
                {"Final extension", "72 °C", hifi ? "2 min" : "5 min", "1"},
                {"Hold", "4 °C", "forever", ""}};
        StringBuilder b = new StringBuilder(String.format(Locale.ROOT, "%-22s %-7s %-10s %s", "Step", "Temp", "Time", "Cycles"));
        for (String[] row : rows) b.append("\n").append(String.format(Locale.ROOT, "%-22s %-7s %-10s %s", (Object[]) row));
        return b.toString();
    }

    static final LinkedHashMap<String, Object[]> ENZYMES = new LinkedHashMap<>();
    static {
        Object[][] t = {{"EcoRI", "GAATTC", 1}, {"BamHI", "GGATCC", 1}, {"HindIII", "AAGCTT", 1}, {"XhoI", "CTCGAG", 1},
                {"NdeI", "CATATG", 2}, {"NcoI", "CCATGG", 1}, {"XbaI", "TCTAGA", 1}, {"SalI", "GTCGAC", 1},
                {"KpnI", "GGTACC", 5}, {"SacI", "GAGCTC", 5}, {"PstI", "CTGCAG", 5}, {"SmaI", "CCCGGG", 3},
                {"NotI", "GCGGCCGC", 2}, {"NheI", "GCTAGC", 1}, {"SpeI", "ACTAGT", 1}, {"BglII", "AGATCT", 1},
                {"EcoRV", "GATATC", 3}, {"ClaI", "ATCGAT", 2}, {"SphI", "GCATGC", 5}, {"ApaI", "GGGCCC", 5},
                {"HaeIII", "GGCC", 2}, {"AluI", "AGCT", 2}, {"MspI", "CCGG", 1}, {"TaqI", "TCGA", 1},
                {"DpnII", "GATC", 0}, {"Sau3AI", "GATC", 0}};
        for (Object[] r : t) ENZYMES.put((String) r[0], new Object[]{r[1], r[2]});
    }

    public static Object enzymes(Object... a) { ArrayList<Object> l = new ArrayList<>(ENZYMES.keySet()); l.sort(EchoRuntime::cmp); return l; }

    public static Object restriction_sites(Object... a) {
        String s = seq(arg(a, 0), "restriction_sites");
        Object which = arg(a, 1, "enzyme_list", null);
        List<?> names = which == null ? new ArrayList<>(ENZYMES.keySet()) : which instanceof String ? list(which) : (List<?>) which;
        LinkedHashMap<Object, Object> out = new LinkedHashMap<>();
        for (Object n : names) {
            Object[] e = ENZYMES.get(show(n));
            if (e == null) throw new EchoError("Unknown enzyme '" + show(n) + "'.");
            ArrayList<Object> pos = new ArrayList<>();
            String site = (String) e[0];
            for (int i = s.indexOf(site); i >= 0; i = s.indexOf(site, i + 1)) pos.add((long) i + (Integer) e[1]);
            if (!pos.isEmpty()) out.put(show(n), pos);
        }
        return out;
    }

    public static Object digest(Object... a) {
        String s = seq(arg(a, 0), "digest");
        Object enz = arg(a, 1, "enzyme", null);
        boolean circ = truthy(arg(a, 2, "circular", false));
        TreeSet<Long> cuts = new TreeSet<>();
        for (Object v : ((Map<?, ?>) restriction_sites(s, enz instanceof String ? list(enz) : enz)).values())
            for (Object p : (List<?>) v) cuts.add(toLong(p));
        ArrayList<Object> frags = new ArrayList<>();
        if (cuts.isEmpty()) { frags.add((long) s.length()); return frags; }
        ArrayList<Long> c = new ArrayList<>(cuts);
        if (circ) {
            for (int i = 0; i + 1 < c.size(); i++) frags.add(c.get(i + 1) - c.get(i));
            frags.add(s.length() - c.get(c.size() - 1) + c.get(0));
        } else {
            c.add(0, 0L); c.add((long) s.length());
            for (int i = 0; i + 1 < c.size(); i++) if (c.get(i + 1) - c.get(i) > 0) frags.add(c.get(i + 1) - c.get(i));
        }
        frags.sort((x, y) -> Long.compare(toLong(y), toLong(x)));
        return frags;
    }

    public static Object align(Object... a) {
        String x = show(arg(a, 0)).toUpperCase(), y = show(arg(a, 1)).toUpperCase();
        long match = toLong(arg(a, 2, "match", 1L)), mis = toLong(arg(a, 3, "mismatch", -1L)), gap = toLong(arg(a, 4, "gap", -2L));
        int n = x.length(), m = y.length();
        long[][] sc = new long[n + 1][m + 1];
        for (int i = 1; i <= n; i++) sc[i][0] = i * gap;
        for (int j = 1; j <= m; j++) sc[0][j] = j * gap;
        for (int i = 1; i <= n; i++) for (int j = 1; j <= m; j++) {
            long d = sc[i - 1][j - 1] + (x.charAt(i - 1) == y.charAt(j - 1) ? match : mis), u = sc[i - 1][j] + gap, l = sc[i][j - 1] + gap;
            sc[i][j] = d >= u && d >= l ? d : (u >= l ? u : l);
        }
        StringBuilder top = new StringBuilder(), mid = new StringBuilder(), bot = new StringBuilder();
        int i = n, j = m;
        while (i > 0 || j > 0) {
            if (i > 0 && j > 0 && sc[i][j] == sc[i - 1][j - 1] + (x.charAt(i - 1) == y.charAt(j - 1) ? match : mis)) {
                top.append(x.charAt(i - 1)); bot.append(y.charAt(j - 1)); mid.append(x.charAt(i - 1) == y.charAt(j - 1) ? '|' : '.'); i--; j--;
            } else if (i > 0 && sc[i][j] == sc[i - 1][j] + gap) { top.append(x.charAt(i - 1)); bot.append('-'); mid.append(' '); i--; }
            else { top.append('-'); bot.append(y.charAt(j - 1)); mid.append(' '); j--; }
        }
        String ms = mid.reverse().toString();
        long same = ms.chars().filter(c -> c == '|').count();
        return mapOf("score", sc[n][m], "a", top.reverse().toString(), "match", ms, "b", bot.reverse().toString(),
                "identity", round2(100.0 * same / Math.max(1, ms.length())), "length", (long) ms.length());
    }

    static final Map<Character, Double> AA_W = new HashMap<>(), KD = new HashMap<>();
    static {
        String aas = "ACDEFGHIKLMNOPQRSTUVWY";
        double[] w = {89.0932, 121.1582, 133.1027, 147.1293, 165.1891, 75.0666, 155.1546, 131.1729, 146.1876, 131.1729,
                149.2113, 132.1179, 255.3134, 115.1305, 146.1445, 174.201, 105.0926, 119.1192, 168.0532, 117.1463, 204.2252, 181.1885};
        for (int i = 0; i < aas.length(); i++) AA_W.put(aas.charAt(i), w[i]);
        String k = "ARNDCQEGHILKMFPSTWYV";
        double[] kd = {1.8, -4.5, -3.5, -3.5, 2.5, -3.5, -3.5, -0.4, -3.2, 4.5, 3.8, -3.9, 1.9, 2.8, -1.6, -0.8, -0.7, -0.9, -1.3, 4.2};
        for (int i = 0; i < k.length(); i++) KD.put(k.charAt(i), kd[i]);
    }

    static String prot(Object v, String fn) {
        if (v instanceof Map && ((Map<?, ?>) v).containsKey("protein")) v = ((Map<?, ?>) v).get("protein");
        String p = show(v).replaceAll("[\\s\\d*]", "").toUpperCase();
        Matcher m = Pattern.compile("[^ACDEFGHIKLMNPQRSTVWYUO]").matcher(p);
        if (m.find()) throw new EchoError(fn + ": '" + m.group() + "' is not an amino-acid letter.");
        return p;
    }

    public static Object protein_mass(Object... a) {
        String p = prot(arg(a, 0), "protein_mass"); if (p.isEmpty()) return 0L;
        double s = 0; for (char c : p.toCharArray()) s += AA_W.get(c);
        return Math.round((s - 18.0153 * (p.length() - 1)) * 10000.0) / 10000.0;
    }

    static double charge(String p, double ph) {
        double nterm = 7.5, cterm = 3.55;
        Map<Character, Double> nt = new HashMap<>();
        nt.put('A', 7.59); nt.put('M', 7.0); nt.put('S', 6.93); nt.put('P', 8.36); nt.put('T', 6.82); nt.put('V', 7.44); nt.put('E', 7.7);
        if (nt.containsKey(p.charAt(0))) nterm = nt.get(p.charAt(0));
        char last = p.charAt(p.length() - 1);
        if (last == 'D') cterm = 4.55; else if (last == 'E') cterm = 4.75;
        double pos = pc(1, nterm, ph) + pc(cnt(p, 'K'), 10.0, ph) + pc(cnt(p, 'R'), 12.0, ph) + pc(cnt(p, 'H'), 5.98, ph);
        double neg = nc(1, cterm, ph) + nc(cnt(p, 'D'), 4.05, ph) + nc(cnt(p, 'E'), 4.45, ph) + nc(cnt(p, 'C'), 9.0, ph) + nc(cnt(p, 'Y'), 10.0, ph);
        return pos - neg;
    }

    static int cnt(String s, char c) { int n = 0; for (char x : s.toCharArray()) if (x == c) n++; return n; }
    static double pc(int n, double pk, double ph) { return n * Math.pow(10, pk) / (Math.pow(10, pk) + Math.pow(10, ph)); }
    static double nc(int n, double pk, double ph) { return n * Math.pow(10, ph) / (Math.pow(10, pk) + Math.pow(10, ph)); }

    public static Object isoelectric_point(Object... a) {
        String p = prot(arg(a, 0), "isoelectric_point");
        double lo = 4.05, hi = 12.0, ph = 7.775;
        if (charge(p, ph) > 0) { lo = ph; while (charge(p, hi) > 0) hi += 2; }
        else { hi = ph; while (charge(p, lo) < 0) lo -= 2; }
        while (hi - lo > 0.0001) { double mid = (lo + hi) / 2; if (charge(p, mid) > 0) lo = mid; else hi = mid; }
        return Math.round((lo + hi) / 2 * 1000.0) / 1000.0;
    }

    public static Object gravy(Object... a) {
        String p = prot(arg(a, 0), "gravy"); double s = 0; int n = 0;
        for (char c : p.toCharArray()) if (KD.containsKey(c)) { s += KD.get(c); n++; }
        return n == 0 ? (Object) 0L : (Object) (Math.round(s / n * 10000.0) / 10000.0);
    }

    public static Object protein_info(Object... a) {
        String p = prot(arg(a, 0), "protein_info");
        return mapOf("protein", p, "length", (long) p.length(), "mass", protein_mass(p), "pi", isoelectric_point(p),
                "gravy", gravy(p), "charge_7", Math.round(charge(p, 7.0) * 1000.0) / 1000.0);
    }

    public static Object dna_mass(Object... a) {
        String s = seq(arg(a, 0), "dna_mass");
        double w = -61.96;
        for (char c : s.toCharArray()) w += c == 'A' ? 313.21 : c == 'C' ? 289.18 : c == 'G' ? 329.21 : c == 'T' ? 304.2 : 308.95;
        if (truthy(arg(a, 1, "double", false))) {
            w += -61.96;
            for (char c : ((String) reverse_complement(s)).toCharArray()) w += c == 'A' ? 313.21 : c == 'C' ? 289.18 : c == 'G' ? 329.21 : c == 'T' ? 304.2 : 308.95;
        }
        return Math.round(w * 100.0) / 100.0;
    }

    public static Object dilute(Object... a) {
        double c1 = toDouble(arg(a, 0)), c2 = toDouble(arg(a, 1)), v2 = toDouble(arg(a, 2));
        if (c1 == 0) throw new EchoError("Stock concentration can't be 0.");
        double r = Math.round(c2 * v2 / c1 * 10000.0) / 10000.0;
        return r == Math.rint(r) ? (Object) (long) r : (Object) r;
    }

    public static Object copy_number(Object... a) {
        return Math.round(toDouble(arg(a, 0)) * 6.022e23 / (toDouble(arg(a, 1)) * 650 * 1e9));
    }

    public static Object parse_fasta(Object... a) {
        ArrayList<Object> recs = new ArrayList<>(); String name = null; StringBuilder b = new StringBuilder();
        for (String line : show(arg(a, 0)).split("\n")) {
            line = line.trim();
            if (line.startsWith(">")) { if (name != null) recs.add(mapOf("name", name, "seq", b.toString().toUpperCase())); name = line.substring(1).trim(); b.setLength(0); }
            else b.append(line.replaceAll("[\\s\\d]", ""));
        }
        if (name != null) recs.add(mapOf("name", name, "seq", b.toString().toUpperCase()));
        else if (b.length() > 0) recs.add(mapOf("name", "sequence", "seq", b.toString().toUpperCase()));
        return recs;
    }

    public static Object to_fasta(Object... a) {
        String s = show(arg(a, 1)); StringBuilder b = new StringBuilder(">" + show(arg(a, 0)) + "\n");
        for (int i = 0; i < s.length(); i += 60) b.append(s, i, Math.min(s.length(), i + 60)).append("\n");
        return b.toString();
    }

    // ---------- gates and bits
    static long b01(Object v) { return truthy(v) ? 1 : 0; }

    public static Object gate(Object... a) {
        String g = show(arg(a, 0)).toLowerCase(); Object x = b01(arg(a, 1)), y = b01(arg(a, 2, "b", 0L));
        switch (g) {
            case "not": return 1 - (Long) x;
            case "and": return and(x, y); case "or": return or(x, y); case "xor": return xor(x, y);
            case "nand": return nand(x, y); case "nor": return nor(x, y); case "xnor": return xnor(x, y);
            default: throw new EchoError("Unknown gate '" + g + "'.");
        }
    }

    public static Object truth_table(Object... a) {
        Object f = arg(a, 0); String title; int n;
        EchoFn call;
        if (f instanceof String) { final String g = ((String) f).toLowerCase(); title = g.toUpperCase(); n = g.equals("not") ? 1 : 2;
            call = x -> gate(g, x[0], x.length > 1 ? x[1] : 0L); }
        else { title = f instanceof NamedFn ? ((NamedFn) f).name : "fn"; n = (int) toLong(arg(a, 1, "inputs", 2L)); final Object ff = f; call = x -> call(ff, x); }
        StringBuilder b = new StringBuilder();
        String letters = "ABCDEFGH".substring(0, n);
        for (int i = 0; i < n; i++) b.append(i > 0 ? " " : "").append(letters.charAt(i));
        b.append(" | ").append(title).append("\n").append(repeat("-", 2L * n)).append("+").append(repeat("-", title.length() + 1));
        for (int i = 0; i < (1 << n); i++) {
            Object[] bits = new Object[n];
            for (int k = 0; k < n; k++) bits[k] = (long) ((i >> (n - 1 - k)) & 1);
            Object r = call.call(bits);
            b.append("\n");
            for (int k = 0; k < n; k++) b.append(k > 0 ? " " : "").append(bits[k]);
            b.append(" | ");
            if (r instanceof Map) { boolean first = true; for (Map.Entry<?, ?> e : ((Map<?, ?>) r).entrySet()) {
                b.append(first ? "" : " ").append(e.getKey()).append("=").append(b01(e.getValue())); first = false; } }
            else b.append(b01(r));
        }
        return b.toString();
    }

    public static Object half_adder(Object... a) { long x = b01(arg(a, 0)), y = b01(arg(a, 1)); return mapOf("sum", x ^ y, "carry", x & y); }

    public static Object full_adder(Object... a) {
        long x = b01(arg(a, 0)), y = b01(arg(a, 1)), c = b01(arg(a, 2));
        return mapOf("sum", x ^ y ^ c, "carry", (x & y) | (c & (x ^ y)));
    }

    public static Object add_binary(Object... a) {
        String x = show(arg(a, 0)), y = show(arg(a, 1));
        if (!(x + y).matches("[01]*")) throw new EchoError("add_binary() needs text made of 0 and 1.");
        int n = Math.max(x.length(), y.length());
        x = repeat("0", n - x.length()) + x; y = repeat("0", n - y.length()) + y;
        long carry = 0; StringBuilder out = new StringBuilder();
        for (int i = n - 1; i >= 0; i--) {
            long p = x.charAt(i) - '0', q = y.charAt(i) - '0';
            out.append(p ^ q ^ carry); carry = (p & q) | (carry & (p ^ q));
        }
        if (carry == 1) out.append('1');
        return out.reverse().toString();
    }

    public static Object bit_and(Object... a) { return toLong(arg(a, 0)) & toLong(arg(a, 1)); }
    public static Object bit_or(Object... a) { return toLong(arg(a, 0)) | toLong(arg(a, 1)); }
    public static Object bit_xor(Object... a) { return toLong(arg(a, 0)) ^ toLong(arg(a, 1)); }
    public static Object bit_not(Object... a) { return (~toLong(arg(a, 0))) & ((1L << toLong(arg(a, 1, "bits", 8L))) - 1); }
    public static Object shift_left(Object... a) { return toLong(arg(a, 0)) << toLong(arg(a, 1)); }
    public static Object shift_right(Object... a) { return toLong(arg(a, 0)) >> toLong(arg(a, 1)); }

    public static Object to_binary(Object... a) {
        String s = Long.toBinaryString(toLong(arg(a, 0))); long bits = toLong(arg(a, 1, "bits", 0L));
        return s.length() < bits ? repeat("0", bits - s.length()) + s : s;
    }

    public static Object from_binary(Object... a) { return Long.parseLong(show(arg(a, 0)).replace(" ", ""), 2); }
    public static Object to_hex(Object... a) { return Long.toHexString(toLong(arg(a, 0))); }
    public static Object from_hex(Object... a) { return Long.parseLong(show(arg(a, 0)).replace("0x", ""), 16); }
    public static Object count_ones(Object... a) { return (long) Long.bitCount(toLong(arg(a, 0))); }

    // ---------- cyber
    static String hash(String algo, Object t) {
        try {
            byte[] d = MessageDigest.getInstance(algo).digest(show(t).getBytes(StandardCharsets.UTF_8));
            StringBuilder b = new StringBuilder(); for (byte x : d) b.append(String.format("%02x", x)); return b.toString();
        } catch (Exception e) { throw new EchoError(e.toString()); }
    }

    public static Object md5(Object... a) { return hash("MD5", arg(a, 0)); }
    public static Object sha1(Object... a) { return hash("SHA-1", arg(a, 0)); }
    public static Object sha256(Object... a) { return hash("SHA-256", arg(a, 0)); }
    public static Object sha512(Object... a) { return hash("SHA-512", arg(a, 0)); }
    public static Object base64_encode(Object... a) { return Base64.getEncoder().encodeToString(show(arg(a, 0)).getBytes(StandardCharsets.UTF_8)); }

    public static Object base64_decode(Object... a) {
        try { return new String(Base64.getDecoder().decode(show(arg(a, 0))), StandardCharsets.UTF_8); }
        catch (IllegalArgumentException e) { throw new EchoError("That is not valid Base64."); }
    }

    public static Object hex_encode(Object... a) {
        StringBuilder b = new StringBuilder(); for (byte x : show(arg(a, 0)).getBytes(StandardCharsets.UTF_8)) b.append(String.format("%02x", x));
        return b.toString();
    }

    public static Object hex_decode(Object... a) {
        String h = show(arg(a, 0)); byte[] out = new byte[h.length() / 2];
        for (int i = 0; i < out.length; i++) out[i] = (byte) Integer.parseInt(h.substring(2 * i, 2 * i + 2), 16);
        return new String(out, StandardCharsets.UTF_8);
    }

    static String shift(String t, long k) {
        StringBuilder b = new StringBuilder();
        for (char c : t.toCharArray()) {
            if (c >= 'a' && c <= 'z') b.append((char) ('a' + Math.floorMod(c - 'a' + k, 26)));
            else if (c >= 'A' && c <= 'Z') b.append((char) ('A' + Math.floorMod(c - 'A' + k, 26)));
            else b.append(c);
        }
        return b.toString();
    }

    public static Object caesar(Object... a) { return shift(show(arg(a, 0)), toLong(arg(a, 1))); }
    public static Object rot13(Object... a) { return shift(show(arg(a, 0)), 13); }

    public static Object caesar_crack(Object... a) {
        ArrayList<Object> out = new ArrayList<>();
        for (int k = 0; k < 26; k++) out.add(String.format(Locale.ROOT, "%2d: %s", k, shift(show(arg(a, 0)), -k)));
        return out;
    }

    public static Object vigenere(Object... a) {
        String t = show(arg(a, 0)), key = show(arg(a, 1)).toUpperCase().replaceAll("[^A-Z]", "");
        boolean dec = truthy(arg(a, 2, "decode", false));
        if (key.isEmpty()) throw new EchoError("vigenere() needs a key with letters.");
        StringBuilder b = new StringBuilder(); int i = 0;
        for (char c : t.toCharArray()) {
            if ((c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z')) { int k = key.charAt(i++ % key.length()) - 'A'; b.append(shift(String.valueOf(c), dec ? -k : k)); }
            else b.append(c);
        }
        return b.toString();
    }

    public static Object entropy(Object... a) {
        String t = show(arg(a, 0)); if (t.isEmpty()) return 0L;
        Map<Character, Integer> c = new HashMap<>(); for (char x : t.toCharArray()) c.merge(x, 1, Integer::sum);
        double h = 0; for (int n : c.values()) { double p = (double) n / t.length(); h -= p * Math.log(p) / Math.log(2); }
        return Math.round(h * 10000.0) / 10000.0;
    }

    public static Object password_strength(Object... a) {
        String pw = show(arg(a, 0)); int pool = 0; ArrayList<Object> tips = new ArrayList<>();
        if (pw.matches(".*[a-z].*")) pool += 26; else tips.add("add lower-case letters");
        if (pw.matches(".*[A-Z].*")) pool += 26; else tips.add("add capital letters");
        if (pw.matches(".*[0-9].*")) pool += 10; else tips.add("add numbers");
        if (pw.matches(".*[^A-Za-z0-9].*")) pool += 32; else tips.add("add symbols");
        if (pw.length() < 12) tips.add("use 12 or more characters");
        double bits = pool == 0 ? 0 : pw.length() * Math.log(pool) / Math.log(2);
        boolean common = Arrays.asList("password", "123456", "12345678", "qwerty", "admin", "letmein", "iloveyou").contains(pw.toLowerCase());
        long score = common ? 0 : bits < 28 ? 0 : bits < 36 ? 1 : bits < 60 ? 2 : bits < 80 ? 3 : 4;
        if (common) tips.add(0, "this is a very common password");
        String[] labels = {"very weak", "weak", "fair", "strong", "very strong"};
        return mapOf("score", score, "label", labels[(int) score], "bits", Math.round(bits * 10.0) / 10.0, "tips", tips);
    }

    public static Object random_password(Object... a) {
        String chars = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789!@#$%^&*-_=+";
        SecureRandom r = new SecureRandom(); StringBuilder b = new StringBuilder();
        for (long i = 0; i < toLong(arg(a, 0, "length", 16L)); i++) b.append(chars.charAt(r.nextInt(chars.length())));
        return b.toString();
    }

    // ---------- statistics
    static List<Double> nums(Object v, String fn) {
        if (!(v instanceof List) || ((List<?>) v).isEmpty()) throw new EchoError(fn + "() needs a non-empty list of numbers.");
        ArrayList<Double> out = new ArrayList<>(); for (Object o : (List<?>) v) out.add(toDouble(o)); return out;
    }

    static Object numOut(double d) { return d == Math.rint(d) && Math.abs(d) < 1e15 ? (Object) d : (Object) d; }

    public static Object mean(Object... a) { double s = 0; List<Double> l = nums(arg(a, 0), "mean"); for (double d : l) s += d; return s / l.size(); }
    public static Object average(Object... a) { return mean(a); }

    public static Object median(Object... a) {
        List<Double> l = nums(arg(a, 0), "median"); Collections.sort(l); int n = l.size();
        return n % 2 == 1 ? l.get(n / 2) : (l.get(n / 2 - 1) + l.get(n / 2)) / 2;
    }

    public static Object variance(Object... a) {
        List<Double> l = nums(arg(a, 0), "variance"); if (l.size() < 2) return 0L;
        double m = toDouble(mean(arg(a, 0))), s = 0; for (double d : l) s += (d - m) * (d - m); return s / (l.size() - 1);
    }

    public static Object stdev(Object... a) { return Math.sqrt(toDouble(variance(a))); }
    public static Object sd(Object... a) { return stdev(a); }

    public static Object correlation(Object... a) {
        List<Double> x = nums(arg(a, 0), "correlation"), y = nums(arg(a, 1), "correlation");
        double mx = toDouble(mean(arg(a, 0))), my = toDouble(mean(arg(a, 1))), sxy = 0, sx = 0, sy = 0;
        for (int i = 0; i < x.size(); i++) { sxy += (x.get(i) - mx) * (y.get(i) - my); sx += Math.pow(x.get(i) - mx, 2); sy += Math.pow(y.get(i) - my, 2); }
        return sx == 0 || sy == 0 ? 0.0 : sxy / Math.sqrt(sx * sy);
    }

    public static Object normalize(Object... a) {
        List<Double> l = nums(arg(a, 0), "normalize"); double lo = Collections.min(l), hi = Collections.max(l);
        ArrayList<Object> out = new ArrayList<>(); for (double d : l) out.add(hi == lo ? 0.0 : (d - lo) / (hi - lo)); return out;
    }

    public static Object linear_fit(Object... a) {
        List<Double> x = nums(arg(a, 0), "linear_fit"), y = nums(arg(a, 1), "linear_fit");
        if (x.size() != y.size() || x.size() < 2) throw new EchoError("linear_fit() needs two lists of the same length (2 or more).");
        double mx = toDouble(mean(arg(a, 0))), my = toDouble(mean(arg(a, 1))), sxx = 0, sxy = 0;
        for (int i = 0; i < x.size(); i++) { sxx += Math.pow(x.get(i) - mx, 2); sxy += (x.get(i) - mx) * (y.get(i) - my); }
        if (sxx == 0) throw new EchoError("linear_fit(): all x values are the same.");
        double slope = sxy / sxx, icept = my - slope * mx, tot = 0, res = 0;
        for (int i = 0; i < x.size(); i++) { tot += Math.pow(y.get(i) - my, 2); res += Math.pow(y.get(i) - (slope * x.get(i) + icept), 2); }
        return mapOf("kind", "linear", "slope", slope, "intercept", icept, "r2", tot == 0 ? 1.0 : 1 - res / tot,
                "weights", list(slope), "bias", icept);
    }

    static List<List<Double>> rows(Object X, String fn) {
        if (!(X instanceof List) || ((List<?>) X).isEmpty()) throw new EchoError(fn + "() needs a list of examples.");
        ArrayList<List<Double>> out = new ArrayList<>();
        for (Object r : (List<?>) X) {
            ArrayList<Double> row = new ArrayList<>();
            if (r instanceof List) for (Object v : (List<?>) r) row.add(toDouble(v)); else row.add(toDouble(r));
            if (!out.isEmpty() && out.get(0).size() != row.size())
                throw new EchoError(fn + "(): every example must have the same number of features.");
            out.add(row);
        }
        return out;
    }

    static double[] solve(double[][] A, double[] b) {
        int n = b.length; double[][] M = new double[n][n + 1];
        for (int i = 0; i < n; i++) { System.arraycopy(A[i], 0, M[i], 0, n); M[i][n] = b[i]; }
        for (int c = 0; c < n; c++) {
            int p = c; for (int r = c; r < n; r++) if (Math.abs(M[r][c]) > Math.abs(M[p][c])) p = r;
            if (Math.abs(M[p][c]) < 1e-12) throw new EchoError("The data can't fit a line (features repeat or too few examples).");
            double[] t = M[c]; M[c] = M[p]; M[p] = t;
            for (int r = 0; r < n; r++) if (r != c) { double f = M[r][c] / M[c][c]; for (int k = c; k <= n; k++) M[r][k] -= f * M[c][k]; }
        }
        double[] x = new double[n]; for (int i = 0; i < n; i++) x[i] = M[i][n] / M[i][i]; return x;
    }

    static double sigmoid(double z) { return z < -60 ? 0 : z > 60 ? 1 : 1 / (1 + Math.exp(-z)); }

    public static Object train(Object... a) {
        String kind = show(arg(a, 0)).toLowerCase();
        List<List<Double>> X = rows(arg(a, 1), "train");
        List<?> y = (List<?>) arg(a, 2);
        if (y == null || y.size() != X.size()) throw new EchoError("train(): y must be a list with one answer per example.");
        int n = X.size(), d = X.get(0).size();
        if (kind.equals("knn")) return mapOf("kind", "knn", "k", toLong(arg(a, 3, "k", 3L)), "X", arg(a, 1), "y", new ArrayList<>(y));
        if (kind.equals("linear")) {
            double[][] A = new double[d + 1][d + 1]; double[] b = new double[d + 1];
            for (int r = 0; r < n; r++) {
                double[] row = new double[d + 1]; for (int j = 0; j < d; j++) row[j] = X.get(r).get(j); row[d] = 1;
                for (int i = 0; i <= d; i++) { for (int j = 0; j <= d; j++) A[i][j] += row[i] * row[j]; b[i] += row[i] * toDouble(y.get(r)); }
            }
            double[] sol = solve(A, b);
            ArrayList<Object> w = new ArrayList<>(); for (int j = 0; j < d; j++) w.add(sol[j]);
            LinkedHashMap<Object, Object> m = mapOf("kind", "linear", "weights", w, "bias", sol[d]);
            double my = 0; for (Object t : y) my += toDouble(t); my /= n;
            double tot = 0, res = 0;
            for (int r = 0; r < n; r++) { double p = toDouble(predict(m, list(X.get(r).toArray()))); tot += Math.pow(toDouble(y.get(r)) - my, 2); res += Math.pow(toDouble(y.get(r)) - p, 2); }
            m.put("r2", tot == 0 ? 1.0 : 1 - res / tot);
            return m;
        }
        if (kind.equals("logistic")) {
            long epochs = toLong(arg(a, 4, "epochs", 2000L)); double rate = toDouble(arg(a, 5, "rate", 0.1));
            double[] mu = new double[d], sd = new double[d];
            for (int j = 0; j < d; j++) {
                double s = 0; for (List<Double> r : X) s += r.get(j); mu[j] = s / n;
                double v = 0; for (List<Double> r : X) v += Math.pow(r.get(j) - mu[j], 2); sd[j] = n > 1 ? Math.sqrt(v / (n - 1)) : 0; if (sd[j] == 0) sd[j] = 1;
            }
            double[] w = new double[d]; double b0 = 0;
            for (long ep = 0; ep < epochs; ep++) {
                double[] gw = new double[d]; double gb = 0;
                for (int r = 0; r < n; r++) {
                    double z = b0; for (int j = 0; j < d; j++) z += w[j] * (X.get(r).get(j) - mu[j]) / sd[j];
                    double err = sigmoid(z) - toDouble(y.get(r));
                    for (int j = 0; j < d; j++) gw[j] += err * (X.get(r).get(j) - mu[j]) / sd[j];
                    gb += err;
                }
                for (int j = 0; j < d; j++) w[j] -= rate * gw[j] / n;
                b0 -= rate * gb / n;
            }
            ArrayList<Object> W = new ArrayList<>(), MU = new ArrayList<>(), SD = new ArrayList<>();
            for (int j = 0; j < d; j++) { W.add(w[j]); MU.add(mu[j]); SD.add(sd[j]); }
            return mapOf("kind", "logistic", "weights", W, "bias", b0, "mean", MU, "scale", SD);
        }
        throw new EchoError("Unknown model kind '" + kind + "'. Use 'linear', 'logistic' or 'knn'.");
    }

    public static Object predict(Object... a) {
        Map<?, ?> m = (Map<?, ?>) arg(a, 0); Object x = arg(a, 1);
        List<?> row = x instanceof List ? (List<?>) x : list(x);
        String kind = show(m.get("kind"));
        if (kind.equals("linear")) {
            List<?> w = (List<?>) m.get("weights");
            double s = toDouble(m.get("bias")); for (int i = 0; i < w.size(); i++) s += toDouble(w.get(i)) * toDouble(row.get(i));
            return s;
        }
        if (kind.equals("logistic")) return probability(m, x) >= 0.5 ? 1L : 0L;
        if (kind.equals("knn")) {
            List<List<Double>> X = rows(m.get("X"), "predict"); List<?> y = (List<?>) m.get("y"); int k = (int) toLong(m.get("k"));
            Integer[] idx = new Integer[X.size()]; for (int i = 0; i < idx.length; i++) idx[i] = i;
            final double[] dist = new double[X.size()];
            for (int i = 0; i < X.size(); i++) { double s = 0; for (int j = 0; j < row.size(); j++) s += Math.pow(X.get(i).get(j) - toDouble(row.get(j)), 2); dist[i] = Math.sqrt(s); }
            Arrays.sort(idx, (p, q) -> Double.compare(dist[p], dist[q]));
            LinkedHashMap<Object, Integer> votes = new LinkedHashMap<>();
            for (int i = 0; i < Math.min(k, idx.length); i++) votes.merge(y.get(idx[i]), 1, Integer::sum);
            Object best = null; int bv = -1;
            for (Map.Entry<Object, Integer> e : votes.entrySet()) if (e.getValue() > bv) { bv = e.getValue(); best = e.getKey(); }
            return best;
        }
        throw new EchoError("predict() needs a model made by train() or linear_fit().");
    }

    static double probability(Map<?, ?> m, Object x) {
        List<?> row = x instanceof List ? (List<?>) x : list(x);
        List<?> w = (List<?>) m.get("weights"), mu = (List<?>) m.get("mean"), sd = (List<?>) m.get("scale");
        double z = toDouble(m.get("bias"));
        for (int j = 0; j < w.size(); j++) z += toDouble(w.get(j)) * (toDouble(row.get(j)) - toDouble(mu.get(j))) / toDouble(sd.get(j));
        return sigmoid(z);
    }

    public static Object probability(Object... a) { return probability((Map<?, ?>) arg(a, 0), arg(a, 1)); }

    public static Object accuracy(Object... a) {
        List<?> X = (List<?>) arg(a, 1), y = (List<?>) arg(a, 2); long right = 0;
        for (int i = 0; i < X.size(); i++) if (eq(predict(arg(a, 0), X.get(i)), y.get(i))) right++;
        return div(right, (long) X.size());
    }

    public static Object cluster(Object... a) {
        List<List<Double>> P = rows(arg(a, 0), "cluster"); int k = (int) toLong(arg(a, 1)); long seed = toLong(arg(a, 2, "seed", 1L));
        if (k < 1 || k > P.size()) throw new EchoError("cluster(): k must be between 1 and the number of points.");
        ArrayList<Integer> order = new ArrayList<>(); for (int i = 0; i < P.size(); i++) order.add(i);
        Collections.shuffle(order, new Random(seed));
        double[][] c = new double[k][]; for (int i = 0; i < k; i++) c[i] = P.get(order.get(i)).stream().mapToDouble(Double::doubleValue).toArray();
        int[] labels = new int[P.size()];
        for (int it = 0; it < 100; it++) {
            int[] nl = new int[P.size()];
            for (int i = 0; i < P.size(); i++) { double best = Double.MAX_VALUE;
                for (int j = 0; j < k; j++) { double s = 0; for (int f = 0; f < c[j].length; f++) s += Math.pow(P.get(i).get(f) - c[j][f], 2); if (s < best) { best = s; nl[i] = j; } } }
            for (int j = 0; j < k; j++) { double[] sum = new double[c[j].length]; int cnt = 0;
                for (int i = 0; i < P.size(); i++) if (nl[i] == j) { cnt++; for (int f = 0; f < sum.length; f++) sum[f] += P.get(i).get(f); }
                if (cnt > 0) for (int f = 0; f < sum.length; f++) c[j][f] = sum[f] / cnt; }
            boolean same = Arrays.equals(nl, labels); labels = nl; if (same && it > 0) break;
        }
        ArrayList<Object> L = new ArrayList<>(); for (int l : labels) L.add((long) l);
        ArrayList<Object> C = new ArrayList<>(); for (double[] row : c) { ArrayList<Object> r = new ArrayList<>(); for (double v : row) r.add(v); C.add(r); }
        return mapOf("labels", L, "centers", C);
    }

    // ---------- gel
    static final long[] LADDER = {10000, 8000, 6000, 5000, 4000, 3000, 2000, 1500, 1000, 750, 500, 250};

    public static Object gel(Object... a) {
        List<?> lanes = (List<?>) arg(a, 0); boolean ladder = truthy(arg(a, 1, "ladder", true));
        ArrayList<List<?>> cols = new ArrayList<>();
        if (ladder) { ArrayList<Object> l = new ArrayList<>(); for (long v : LADDER) l.add(v); cols.add(l); }
        if (!lanes.isEmpty() && !(lanes.get(0) instanceof List)) cols.add(lanes); else for (Object l : lanes) cols.add((List<?>) l);
        int rows = 24; double lo = Math.log10(100), hi = Math.log10(12000);
        StringBuilder b = new StringBuilder("  ");
        for (int c = 0; c < cols.size(); c++) {
            String name = ladder && c == 0 ? "Ladder" : "Lane " + (ladder ? c : c + 1);
            b.append(c > 0 ? " " : "").append(String.format(Locale.ROOT, "%-7s", name.length() > 7 ? name.substring(0, 7) : name));
        }
        b.append("\n  ");
        for (int c = 0; c < cols.size(); c++) b.append(c > 0 ? " " : "").append("  ▔▔▔  ");
        for (int r = 0; r < rows; r++) {
            b.append("\n  "); long top = -1;
            for (int c = 0; c < cols.size(); c++) {
                boolean band = false;
                for (Object v : cols.get(c)) {
                    double bp = Math.min(Math.max(toDouble(v), 100), 12000);
                    if (Math.round((hi - Math.log10(bp)) / (hi - lo) * (rows - 1)) == r) { band = true; if (ladder && c == 0) top = Math.max(top, toLong(v)); }
                }
                b.append(c > 0 ? " " : "").append(band ? "  ███  " : "       ");
            }
            if (top >= 0) b.append("  ").append(top).append(" bp");
        }
        return b.toString();
    }

    // ---------- AI (your own key; set with EchoRuntime.aiProvider / aiKey, or env ECHO_AI_PROVIDER / ECHO_AI_KEY)
    public static String aiProvider = System.getenv("ECHO_AI_PROVIDER");
    public static String aiKey = System.getenv("ECHO_AI_KEY");
    public static String aiModel = System.getenv("ECHO_AI_MODEL");

    public static Object ai(Object... a) {
        String prompt = show(arg(a, 0));
        if (aiKey == null || aiKey.isEmpty()) throw new EchoError("E502", "No AI key set. Set EchoRuntime.aiKey (or ECHO_AI_KEY).");
        String p = aiProvider == null ? "claude" : aiProvider.toLowerCase();
        try {
            if (p.equals("claude") || p.equals("anthropic")) {
                String body = "{\"model\":" + json(aiModel == null ? "claude-haiku-5-5" : aiModel)
                        + ",\"max_tokens\":1500,\"messages\":[{\"role\":\"user\",\"content\":" + json(prompt) + "}]}";
                String r = post("https://api.anthropic.com/v1/messages", body, "x-api-key", aiKey, "anthropic-version", "2023-06-01");
                return firstText(r);
            }
            if (p.equals("gemini") || p.equals("google")) {
                String model = aiModel == null ? "gemini-2.5-flash" : aiModel;
                String body = "{\"contents\":[{\"parts\":[{\"text\":" + json(prompt) + "}]}]}";
                return firstText(post("https://generativelanguage.googleapis.com/v1beta/models/" + model + ":generateContent", body, "x-goog-api-key", aiKey));
            }
            String body = "{\"model\":" + json(aiModel == null ? "gpt-4o-mini" : aiModel) + ",\"messages\":[{\"role\":\"user\",\"content\":" + json(prompt) + "}]}";
            String r = post("https://api.openai.com/v1/chat/completions", body, "authorization", "Bearer " + aiKey);
            Matcher m = Pattern.compile("\"content\"\\s*:\\s*\"((?:[^\"\\\\]|\\\\.)*)\"").matcher(r);
            return m.find() ? unjson(m.group(1)) : r;
        } catch (EchoError e) { throw e; } catch (Exception e) { throw new EchoError("AI request failed: " + e.getMessage()); }
    }

    static String firstText(String r) {
        Matcher m = Pattern.compile("\"text\"\\s*:\\s*\"((?:[^\"\\\\]|\\\\.)*)\"").matcher(r);
        return m.find() ? unjson(m.group(1)).trim() : r;
    }

    static String post(String url, String body, String... headers) throws Exception {
        HttpURLConnection c = (HttpURLConnection) new URL(url).openConnection();
        c.setRequestMethod("POST"); c.setDoOutput(true); c.setConnectTimeout(20000); c.setReadTimeout(90000);
        c.setRequestProperty("content-type", "application/json");
        for (int i = 0; i + 1 < headers.length; i += 2) c.setRequestProperty(headers[i], headers[i + 1]);
        try (OutputStream o = c.getOutputStream()) { o.write(body.getBytes(StandardCharsets.UTF_8)); }
        int code = c.getResponseCode();
        java.io.InputStream is = code < 400 ? c.getInputStream() : c.getErrorStream();
        StringBuilder b = new StringBuilder();
        try (BufferedReader r = new BufferedReader(new InputStreamReader(is, StandardCharsets.UTF_8))) { String l; while ((l = r.readLine()) != null) b.append(l).append('\n'); }
        if (code == 401 || code == 403) throw new EchoError("The AI service rejected the key (" + code + ").");
        if (code >= 400) throw new EchoError("AI service error " + code + ": " + b.substring(0, Math.min(300, b.length())));
        return b.toString();
    }

    static String json(String s) {
        StringBuilder b = new StringBuilder("\"");
        for (char c : s.toCharArray()) {
            switch (c) {
                case '"': b.append("\\\""); break; case '\\': b.append("\\\\"); break;
                case '\n': b.append("\\n"); break; case '\r': b.append("\\r"); break; case '\t': b.append("\\t"); break;
                default: if (c < 0x20) b.append(String.format("\\u%04x", (int) c)); else b.append(c);
            }
        }
        return b.append('"').toString();
    }

    static String unjson(String s) {
        StringBuilder b = new StringBuilder();
        for (int i = 0; i < s.length(); i++) {
            char c = s.charAt(i);
            if (c == '\\' && i + 1 < s.length()) {
                char n = s.charAt(++i);
                switch (n) {
                    case 'n': b.append('\n'); break; case 't': b.append('\t'); break; case 'r': break;
                    case 'u': b.append((char) Integer.parseInt(s.substring(i + 1, i + 5), 16)); i += 4; break;
                    default: b.append(n);
                }
            } else b.append(c);
        }
        return b.toString();
    }
}
