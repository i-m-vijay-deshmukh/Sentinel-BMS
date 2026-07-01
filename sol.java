import java.util.Scanner;

public class sol {
    public static void main(String[] args) {
        Scanner sc = new Scanner(System.in);
        int t = sc.nextInt();
        
        while (t-- > 0) {
            int n = sc.nextInt();
            
            int max = Integer.MIN_VALUE;
            int min = Integer.MAX_VALUE;
            for (int i = 0; i < n; i++) {
                int h = sc.nextInt();
                if (h > max) {
                    max = h;
                }
                if (h < min) {
                    min = h;
                }
            }
            int minK = max + 1 - min;
            System.out.println(minK);
        }
    }
}