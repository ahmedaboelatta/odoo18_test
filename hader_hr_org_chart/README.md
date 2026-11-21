# HR Org Chart Interactive — المخطط التنظيمي

أدون لأودو 18 يعرض الهيكل التنظيمي (Hierarchy) للموظفين داخل الشركة على شكل
مخطط شجري واضح وتفاعلي، مع عرض شجرة الأقسام.

## المميزات

- **مخطط الموظفين**: مبني على المدير المباشر (`parent_id`) لكل موظف، مع صورة
  الموظف والمسمى الوظيفي والقسم.
- **مخطط الأقسام**: شجرة الأقسام مع مدير كل قسم وعدد الموظفين فيه.
- **فلتر بالأقسام**: عند اختيار قسم يظهر موظفوه + سلسلة مديريهم حتى القمة،
  عشان الشجرة تفضل متصلة. المديرون من خارج القسم يظهرون بعلامة "خارج القسم".
- **بحث**: بالاسم أو المسمى الوظيفي، مع توسيع تلقائي للفروع حتى تظهر النتائج،
  و `Enter` للانتقال لأول نتيجة.
- **توسيع / طي الفروع**، **سحب وتحريك**، **تقريب وتبعيد** بعجلة الفأرة أو
  الأزرار، وزر **ملاءمة الشاشة**.
- **لوحة تفاصيل**: اضغط على أي موظف لعرض مديره المباشر ومرؤوسيه وبريده
  وهاتفه، واضغط مرتين لفتح بطاقته.
- **طباعة** المخطط.
- لو فيه مشكلة في بيانات المديرين (مثلاً مدير يشير لنفسه أو حلقة مغلقة)
  الموظفون المتأثرون يظهرون في صف إضافي أسفل المخطط بدل ما يختفوا.

## التركيب (Odoo 18)

1. انسخ مجلد `hader_hr_org_chart` إلى مجلد الإضافات (addons path) في سيرفر أودو.
   - في Odoo.sh: ضعه في مستودع الإضافات المخصصة.
   - ملاحظة: الأدون لا يعمل على Odoo Online (SaaS) لأنه لا يقبل أكواد مخصصة.
2. أعد تشغيل خدمة أودو.
3. من داخل أودو: **التطبيقات (Apps)** ← **تحديث قائمة التطبيقات (Update Apps List)**.
4. ابحث عن **HR Org Chart Interactive** وثبّته (Install).
5. افتح القائمة: **الموظفون (Employees)** ← **المخطط التنظيمي**.

للتحديث بعد أي تعديل على الكود: أعد التشغيل ثم حدّث الأدون من قائمة
التطبيقات (Upgrade)، أو من سطر الأوامر: `odoo-bin -u hader_hr_org_chart -d <database>`.

## ملاحظات

- اسم الأدون التقني `hader_hr_org_chart` (وليس `hr_org_chart`) لأن أودو
  Enterprise فيه أصلاً أدون بنفس الاسم `hr_org_chart` ("Org Chart Widget for
  HR" من Odoo S.A.)، ولو استخدمنا نفس الاسم أودو هيحمّل أدون Enterprise
  ويتجاهل ده تماماً. البادئة `hader_` تمنع التضارب ده.
- الأدون يعتمد على تطبيق **الموظفين (hr)** ويقرأ فقط بيانات الدليل العام
  (الاسم، المسمى، القسم، المدير، البريد والهاتف الوظيفي، الصورة). لا يستخدم
  أي بيانات رواتب أو بيانات خاصة.
- ظهور الموظفين في المخطط يعتمد على حقل **المدير (Manager)** في بطاقة كل
  موظف. الموظفون بدون مدير يظهرون كجذور في أعلى المخطط.
- واجهة الأدون بالعربية. لتغيير اللغة أو إضافة ترجمات، عدّل ملف
  `static/src/hader_org_chart/org_chart.xml`.

## البنية

```
hader_hr_org_chart/
├── __manifest__.py
├── models/hr_employee.py          # get_hader_org_chart_data + get_hader_department_chart_data
├── views/hader_hr_org_chart_views.xml   # القائمة + الـ client action
└── static/src/hader_org_chart/
    ├── org_chart.js               # مكوّن Owl + حساب تخطيط الشجرة
    ├── org_chart.xml              # القوالب
    └── org_chart.scss             # التنسيقات
```

---

## HR Org Chart Interactive (English summary)

Interactive org chart addon for **Odoo 18**: employee hierarchy (based on
each employee's Manager), department tree, department filter, search,
expand/collapse, pan & zoom, detail panel, and print. Install it like any
custom addon (copy to your addons path, restart, Update Apps List, install),
then open **Employees → المخطط التنظيمي (Org Chart)**.
