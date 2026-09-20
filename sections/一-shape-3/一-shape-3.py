#
#           DFC Script
# =============================
#   Description: 一-shape-3 - 三折线基准
#          Date: 2026-08-19
#       Version: 1.0
#
    S_1 = theModel.createSect( sectionName = "一-shape-3");
    S_1_SP_1 = theModel.createSecNode( x = 0.000, y = 0.000, z = 0.000, theSect = S_1);
    S_1_SP_2 = theModel.createSecNode( x = -1.610, y = -30.660, z = 0.000, theSect = S_1);
    S_1_SP_3 = theModel.createSecNode( x = -2.160, y = -41.060, z = 6.000, theSect = S_1);
    S_1_SP_4 = theModel.createSecNode( x = -3.220, y = -61.280, z = 6.000, theSect = S_1);
    S_1_SL_1 = theModel.createSecCurve( start = S_1_SP_1, end = S_1_SP_2, theSect = S_1);
    S_1_SL_2 = theModel.createSecCurve( start = S_1_SP_2, end = S_1_SP_3, theSect = S_1);
    S_1_SL_3 = theModel.createSecCurve( start = S_1_SP_3, end = S_1_SP_4, theSect = S_1);
    theModel.drawModel();
