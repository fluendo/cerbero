#include <mono/metadata/assembly.h>
#include <glib.h>

static void custom_init ()
{
  gchar *win_path, *exe_path, *mono_path, *lgm_path, *lib_path;
  gchar *mono_lib_path, *mono_lib_facades_path, *etc_path;
  gchar *gtk_path, *gst_path;

  exe_path = g_win32_get_package_installation_directory_of_module (NULL);
  lib_path = g_build_filename (exe_path, "lib", NULL);
  etc_path = g_build_filename (exe_path, "etc", NULL);
  mono_lib_path = g_build_filename (exe_path, "lib", "mono", "4.5",
      NULL);
  mono_lib_facades_path = g_build_filename (mono_lib_path, "Facades", NULL);
  gtk_path  = g_build_filename (exe_path, "lib",
      "gtk-sharp-2.0", NULL);
  lgm_path = g_build_filename (exe_path, "lib", "longomatch", NULL);
  gst_path = g_build_filename (exe_path, "lib", "longomatch", "plugins", "gstreamer-0.10", NULL);
  win_path = g_strdup_printf ("%s;%s", g_getenv ("PATH"), gst_path);

  g_setenv ("PATH", win_path, TRUE);
  mono_path = g_strdup_printf("%s;%s;%s;%s", mono_lib_path,
      mono_lib_facades_path, gtk_path, lgm_path);
  g_setenv ("MONO_PATH", mono_path, TRUE);
  mono_set_dirs (lib_path, etc_path);
  g_print ("Using PATH %s\n", win_path);
  g_print ("Using MONO_PATH %s\n", mono_path);
}
