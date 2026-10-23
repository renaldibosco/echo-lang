# Python (Chaquopy) calls these classes by name, so R8 must keep them as they are.
-keep class com.renaldibosco.echolang.** { *; }
-keepclassmembers class com.renaldibosco.echolang.** { public *; }
-keep class com.chaquo.python.** { *; }
-dontwarn com.chaquo.python.**
