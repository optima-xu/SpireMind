using System.Reflection;
var directory = args[0];
AppDomain.CurrentDomain.AssemblyResolve += (_, e) => {
    var path = Path.Combine(directory, new AssemblyName(e.Name).Name + ".dll");
    return File.Exists(path) ? Assembly.LoadFrom(path) : null;
};
var assembly = Assembly.LoadFrom(Path.Combine(directory, "sts2.dll"));
Type[] types;
try { types = assembly.GetTypes(); }
catch (ReflectionTypeLoadException e) { types = e.Types.Where(t => t != null).ToArray()!; }
foreach (var t in types.Where(t => args.Skip(1).Contains(t.Name))) {
    Console.WriteLine(t.FullName);
    foreach (var m in t.GetMembers(BindingFlags.Public|BindingFlags.Instance|BindingFlags.Static)
        ) Console.WriteLine("  " + m);
}
