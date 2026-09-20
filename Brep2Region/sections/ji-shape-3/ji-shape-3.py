#
#           DFC Script
# =============================
#   Description: ji-shape-3 (几字形-3) - 非对称多折壁几字形截面
#                基准: S_356 (BAIC B31 前围裙边梁左段)
#          Date: 2026-08-07
#       Version: 4.4.34
#
    S_1 = theModel.createSect( sectionName = "ji-shape-3");
    S_1_SP_1 = theModel.createSecNode( x = 0.00, y = -97.449, z = -38.240, theSect = S_1);
    S_1_SP_2 = theModel.createSecNode( x = 0.00, y = -76.878, z = -31.556, theSect = S_1);
    S_1_SP_3 = theModel.createSecNode( x = 0.00, y = -65.348, z = -30.102, theSect = S_1);
    S_1_SP_4 = theModel.createSecNode( x = 0.00, y = -7.454, z = -6.205, theSect = S_1);
    S_1_SP_5 = theModel.createSecNode( x = 0.00, y = 2.782, z = 9.259, theSect = S_1);
    S_1_SP_6 = theModel.createSecNode( x = 0.00, y = 2.782, z = 85.164, theSect = S_1);
    S_1_SP_7 = theModel.createSecNode( x = 0.00, y = -1.347, z = 96.205, theSect = S_1);
    S_1_SP_8 = theModel.createSecNode( x = 0.00, y = -38.932, z = 139.420, theSect = S_1);
    S_1_SP_9 = theModel.createSecNode( x = 0.00, y = -45.584, z = 150.425, theSect = S_1);
    S_1_SP_10 = theModel.createSecNode( x = 0.00, y = -44.041, z = 168.059, theSect = S_1);
    S_1_SL_1 = theModel.createSecCurve( start = S_1_SP_1, end = S_1_SP_2, theSect = S_1);
    S_1_SL_2 = theModel.createSecCurve( start = S_1_SP_2, end = S_1_SP_3, theSect = S_1);
    S_1_SL_3 = theModel.createSecCurve( start = S_1_SP_3, end = S_1_SP_4, theSect = S_1);
    S_1_SL_4 = theModel.createSecCurve( start = S_1_SP_4, end = S_1_SP_5, theSect = S_1);
    S_1_SL_5 = theModel.createSecCurve( start = S_1_SP_5, end = S_1_SP_6, theSect = S_1);
    S_1_SL_6 = theModel.createSecCurve( start = S_1_SP_6, end = S_1_SP_7, theSect = S_1);
    S_1_SL_7 = theModel.createSecCurve( start = S_1_SP_7, end = S_1_SP_8, theSect = S_1);
    S_1_SL_8 = theModel.createSecCurve( start = S_1_SP_8, end = S_1_SP_9, theSect = S_1);
    S_1_SL_9 = theModel.createSecCurve( start = S_1_SP_9, end = S_1_SP_10, theSect = S_1);
    theModel.drawModel();
